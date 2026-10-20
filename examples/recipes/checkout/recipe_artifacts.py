# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Generates every captured-output artifact the pages under ``documentation/recipes/`` embed.

Rule 8 (docs as tests): each recipe page's code is this directory's source and each output block is
a file a *real run* of that source wrote -- a fixture module run in its own pytest process, with
``narrativetrace-pytest`` loaded, exactly as a reader's ``pytest`` run would be. Nothing is typed
into a page. ``examples/recipes/checkout/build/`` (git-ignored) holds the results;
``test_recipes.py`` asserts on what each run did, and
``packages/narrativetrace/tests/test_snippet_check.py`` calls :func:`write_artifacts` itself so
``poe snippet-check`` never reads a stale or missing file (pytest collects ``packages`` before
``examples``, and a pristine checkout has no ``build/`` at all).

``narrativetrace-pytest``'s ``NARRATIVETRACE_*`` environment channels are scrubbed from the child
process and set explicitly per run, so a developer's own shell can never change a page's output.
The approved baselines are committed under ``test-narratives/`` and copied into ``build/`` before
an approval run: a mismatch writes a ``.received.nt`` beside the baseline, and a verification step
may not write where the repository lives -- which also keeps the paths in the rejection message
stable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from examples.recipes.checkout.env import (
    ARTIFACTS_ENV,
    CORRELATION_LOG_FILE_ENV,
    LOG_FILE_ENV,
    REFACTORED_ENV,
    VERDICTS_ENV,
)

HERE = Path(__file__).parent
REPO_ROOT = HERE.parents[2]
BUILD_DIR = HERE / "build"
APPROVED_DIR = HERE / "test-narratives"
_PACKAGE = "examples.recipes.checkout"

ADD_LOGGING = "add-logging-to-this-service"
DEBUG = "help-me-debug-and-fix-this-bug"
TEST_FAILURE = "why-did-this-test-fail"
REVIEW_FLOW = "review-a-complex-flow-before-changing-it"
REFACTORING = "review-a-refactoring-did-behaviour-change"
ACROSS_SERVICES = "follow-one-request-across-services"
KEEP_OUT_OF_LOGS = "keep-secrets-out-of-the-logs"
ACROSS_THREADS = "follow-a-flow-across-threads"
OBSERVABILITY = "send-traces-to-the-observability-stack-you-already-run"
COST = "trace-in-production-without-the-cost"


@dataclass(frozen=True, slots=True)
class Verdict:
    """What the runner reported for one failing phase of one test."""

    test: str
    when: str
    message: str


@dataclass(frozen=True, slots=True)
class Run:
    """One pytest process: its exit code and every failing phase it reported."""

    exit_code: int
    verdicts: list[Verdict]


def page_dir(slug: str) -> Path:
    """Where one page's generated files live (one directory per page, so no two runs can claim
    the same artifact)."""
    return BUILD_DIR / slug


def _environment(settings: dict[str, str]) -> dict[str, str]:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("NARRATIVETRACE_")}
    return {**inherited, "PYTHONIOENCODING": "utf-8", **settings}


def _run_fixture(module: str, settings: dict[str, str], test: str | None = None) -> Run:
    """Runs ``<module>_fixture.py`` (or just its test ``test``) as a real, separate pytest process
    and reads its verdicts."""
    verdicts_file = Path(settings[VERDICTS_ENV])
    verdicts_file.parent.mkdir(parents=True, exist_ok=True)
    verdicts_file.unlink(missing_ok=True)
    result = subprocess.run(  # nosec B603 - fixed argv, no shell, no untrusted input
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "narrativetrace",
            "-p",
            f"{_PACKAGE}.verdict_plugin",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            f"--rootdir={REPO_ROOT}",
            f"examples/recipes/checkout/{module}_fixture.py" + (f"::{test}" if test else ""),
        ],
        cwd=REPO_ROOT,
        env=_environment(settings),
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    verdicts = _read_verdicts(verdicts_file)
    if result.returncode not in (0, 1):  # 1 is "tests failed"; anything else is a broken run
        raise RuntimeError(f"{module} fixture could not run:\n{result.stdout}\n{result.stderr}")
    return Run(result.returncode, verdicts)


def _read_verdicts(path: Path) -> list[Verdict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Verdict(**json.loads(line)) for line in lines]


def _settings(slug: str, subdir: str = "", **extra: str) -> dict[str, str]:
    base = page_dir(slug) / subdir if subdir else page_dir(slug)
    return {
        "NARRATIVETRACE_OUTPUT_DIR": str(base),
        VERDICTS_ENV: str(base / "verdicts.jsonl"),
        **extra,
    }


def _fresh_approved_dir(slug: str, name: str, module: str) -> Path:
    """The committed baselines of ``<module>_fixture``, alone, in a directory of this run's own --
    emptied first, and named relative to the repository so the rejection message is stable."""
    target = page_dir(slug) / name
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(APPROVED_DIR / f"{module}_fixture", target / f"{module}_fixture")
    return target.relative_to(REPO_ROOT)


def _run_under_approval(
    slug: str, name: str, module: str, test: str | None = None, **extra: str
) -> Run:
    approved = _fresh_approved_dir(slug, name, module)
    settings = _settings(
        slug,
        name + "-output",
        NARRATIVETRACE_APPROVAL="true",
        NARRATIVETRACE_APPROVED_DIR=str(approved),
        **extra,
    )
    return _run_fixture(module, settings, test)


@dataclass(frozen=True, slots=True)
class RecipeRuns:
    """Every run the pages draw on, for ``test_recipes.py`` to assert on."""

    add_logging: Run
    debug: Run
    debug_under_approval: Run
    test_failure: Run
    review_detail: Run
    review_summary: Run
    refactoring_as_shipped: Run
    refactoring_dropped_the_release: Run
    across_services: Run
    secrets: Run
    across_threads: Run
    without_handover: Run
    observability: Run
    cost_detail: Run
    cost_errors: Run
    cost_detail_successful: Run
    cost_errors_successful: Run


@cache
def write_artifacts() -> RecipeRuns:
    """Runs every recipe fixture and writes the files the pages embed -- idempotent, and safe to
    call from more than one test (the work is done once per process)."""
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    return RecipeRuns(
        add_logging=_add_logging(),
        debug=_run_fixture("declined_payment", _settings(DEBUG)),
        debug_under_approval=_debug_under_approval(),
        test_failure=_test_failure(),
        review_detail=_review_flow("detail"),
        review_summary=_review_flow("summary", NARRATIVETRACE_LEVEL="SUMMARY"),
        **_refactoring(),
        across_services=_across_services(),
        secrets=_secrets(),
        **_across_threads(),
        observability=_observability(),
        **_cost(),
    )


def _add_logging() -> Run:
    log = page_dir(ADD_LOGGING) / "checkout.log"
    return _run_fixture("add_logging", _settings(ADD_LOGGING, **{LOG_FILE_ENV: str(log)}))


def _debug_under_approval() -> Run:
    """The fixed reproduction against its committed baseline -- the page's "pinned" claim."""
    return _run_under_approval(
        DEBUG,
        "approved",
        "declined_payment",
        "test_the_stock_is_released_when_the_card_is_declined",
    )


def _test_failure() -> Run:
    run = _run_fixture("stale_expectation", _settings(TEST_FAILURE))
    (page_dir(TEST_FAILURE) / "assertion-failure.txt").write_text(
        run.verdicts[0].message.strip() + "\n", encoding="utf-8"
    )
    return run


def _review_flow(detail_or_summary: str, **extra: str) -> Run:
    """One successful checkout; the DETAIL run also writes the log lines the page sets beside the
    structural trace."""
    log = page_dir(REVIEW_FLOW) / detail_or_summary / "checkout.log"
    return _run_fixture(
        "checkout_review",
        _settings(REVIEW_FLOW, detail_or_summary, **{LOG_FILE_ENV: str(log)}, **extra),
    )


def _refactoring() -> dict[str, Run]:
    shipped = _run_under_approval(REFACTORING, "approved-as-shipped", "refactored_checkout")
    dropped = _run_under_approval(
        REFACTORING,
        "approved-after-the-refactoring",
        "refactored_checkout",
        **{REFACTORED_ENV: "true"},
    )
    rejection = dropped.verdicts[0].message
    (page_dir(REFACTORING) / "approval-rejection.txt").write_text(
        rejection.strip() + "\n", encoding="utf-8"
    )
    return {"refactoring_as_shipped": shipped, "refactoring_dropped_the_release": dropped}


def _across_services() -> Run:
    """Two services' lines in one file, and the two narratives the page sets beside them."""
    log = page_dir(ACROSS_SERVICES) / "checkout.log"
    artifacts = str(page_dir(ACROSS_SERVICES))
    return _run_fixture(
        "across_services",
        _settings(
            ACROSS_SERVICES, **{CORRELATION_LOG_FILE_ENV: str(log), ARTIFACTS_ENV: artifacts}
        ),
    )


def _secrets() -> Run:
    """One checkout carrying a password and a card; the fixture reads the log back itself."""
    log = page_dir(KEEP_OUT_OF_LOGS) / "checkout.log"
    return _run_fixture("secrets", _settings(KEEP_OUT_OF_LOGS, **{LOG_FILE_ENV: str(log)}))


def _across_threads() -> dict[str, Run]:
    """The wrapped run, whose log and structure the page embeds, and the same submit without the
    handover -- a run of its own, because its trace id is fresh every time."""
    kept = _threads_settings()
    lost = _threads_settings("no-handover")
    return {
        "across_threads": _run_fixture(
            "across_threads", kept, "test_the_background_tasks_stay_in_the_customers_trace"
        ),
        "without_handover": _run_fixture(
            "across_threads",
            lost,
            "test_a_task_submitted_without_the_handover_starts_a_new_trace",
        ),
    }


def _threads_settings(subdir: str = "") -> dict[str, str]:
    base = page_dir(ACROSS_THREADS) / subdir if subdir else page_dir(ACROSS_THREADS)
    return _settings(
        ACROSS_THREADS,
        subdir,
        **{CORRELATION_LOG_FILE_ENV: str(base / "checkout.log"), ARTIFACTS_ENV: str(base)},
    )


def _observability() -> Run:
    """The log lines and the exported spans of one run, side by side."""
    log = page_dir(OBSERVABILITY) / "checkout.log"
    artifacts = str(page_dir(OBSERVABILITY))
    return _run_fixture(
        "observability",
        _settings(OBSERVABILITY, **{LOG_FILE_ENV: str(log), ARTIFACTS_ENV: artifacts}),
    )


# snippet:begin cost
def _cost() -> dict[str, Run]:
    """The declined-payment reproduction at both levels, and a checkout that succeeds at both."""
    declined = "test_the_stock_is_released_when_the_card_is_declined"
    return {
        "cost_detail": _at_level("detail", "declined_payment", declined),
        "cost_errors": _at_level("errors", "declined_payment", declined, level="ERRORS"),
        "cost_detail_successful": _at_level("detail-successful", "checkout_review"),
        "cost_errors_successful": _at_level("errors-successful", "checkout_review", level="ERRORS"),
    }


def _at_level(directory: str, module: str, test: str | None = None, level: str = "DETAIL") -> Run:
    """One fixture run into its own directory, at ``level`` (the default level is DETAIL)."""
    return _run_fixture(module, _settings(COST, directory, NARRATIVETRACE_LEVEL=level), test)
    # snippet:end cost


if __name__ == "__main__":
    write_artifacts()
