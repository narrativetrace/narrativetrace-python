# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier B fuzz entry point (`poe fuzz`) — makes a suspiciously fast or suspiciously small run
impossible to mistake for success.

atheris (Python's libFuzzer-backed coverage-guided fuzzer, Java's Jazzer analogue) is checked for
importability first. Where it is (verified 2026-09-09: only a plain `x86_64` Linux CPython
3.12-3.14 interpreter — not this repo's own `.devcontainer`, not any macOS host; see
`documentation/security-testing.md` for the dated evidence), this script runs a real, time-boxed
coverage-guided fuzz of target 1 (`atheris_traceparent_target.py`) and reports what it actually
executed — a genuine crash fails the run, exactly as it should. Target 2 has no atheris harness
yet (its input is an object graph, not a byte string). Either way, this script then runs the same
budgeted Hypothesis sweep `poe fuzz` has always run over both targets, and makes its own honesty
checkable: it parses Hypothesis's own `--hypothesis-show-statistics` output for the number of
examples each property actually executed, sums them, and FAILS below a floor. This is exactly the
failure class the team already caught once for real (`python-fuzz` reporting "OK" in 16 seconds
against a budget that cannot finish that fast) — a run that collected zero tests, crashed before
generating anything, or otherwise did nothing while still exiting 0.

Every outcome — which tier ran, how many examples/executions, how long it took — is printed,
never silent.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_ATHERIS_TARGET = (
    REPO_ROOT
    / "packages"
    / "narrativetrace-security-tests"
    / "tests"
    / "atheris_traceparent_target.py"
)
_ATHERIS_BUDGET_SECONDS = 60
# Real measured throughput on the verified run (documentation/security-testing.md) was ~4,400
# executions/sec; this floor is set far below that so slower CI hardware never makes a genuine
# run look fake, while still catching "the harness crashed immediately and executed nothing."
_ATHERIS_MINIMUM_EXEC_PER_SECOND = 50

# The two priority hostile-input targets `poe fuzz` sweeps (documentation/security-testing.md's
# target-priority table, targets 1 and 2).
_FUZZ_TEST_PATHS = (
    "packages/narrativetrace-security-tests/tests/test_traceparent_properties.py",
    "packages/narrativetrace-security-tests/tests/test_value_renderer_redaction_properties.py",
)

# Eight `@fuzz_settings`-decorated properties exist today, six of them budgeted at 5,000 examples
# and two capped lower by Hypothesis itself (a small, exhaustible input space) — roughly 31,200
# examples for a genuine run on the current suite. The floor sits well below that so a change to
# the suite's own size does not make this brittle, and well above what any collection failure,
# import error, or crashed-before-generating run could produce.
_MINIMUM_TOTAL_EXAMPLES = 20_000

_STATISTICS_LINE = re.compile(
    r"-\s*(\d+) passing examples?,\s*(\d+) failing examples?,\s*(\d+) invalid examples?"
)
_ATHERIS_EXEC_COUNT = re.compile(r"stat::number_of_executed_units:\s*(\d+)")


def module_importable(name: str) -> bool:
    """Whether `name` can be imported in this interpreter, without actually importing it."""
    return importlib.util.find_spec(name) is not None


def atheris_status_message(available: bool) -> str:
    """The line printed before the sweep runs, naming which tier this invocation is really doing."""
    if available:
        return (
            "TIER B: atheris IS importable on this interpreter — running a real, time-boxed "
            "coverage-guided fuzz of target 1 (atheris_traceparent_target.py), plus the "
            "Hypothesis fallback over both targets."
        )
    return (
        "TIER B: atheris is not importable on this interpreter/platform — running the budgeted "
        "Hypothesis fallback (documentation/security-testing.md has the current, dated evidence "
        "for why, and what would have to be true for that to change)."
    )


def parse_atheris_executions(atheris_output: str) -> int | None:
    """The `stat::number_of_executed_units` libFuzzer prints, or None if it never printed one
    (a harness that crashed or failed to start before finishing its own stats block)."""
    match = _ATHERIS_EXEC_COUNT.search(atheris_output)
    return int(match.group(1)) if match else None


def parse_example_counts(hypothesis_statistics_output: str) -> list[int]:
    """Every per-property example count (passing + failing + invalid) Hypothesis reported."""
    return [
        int(passing) + int(failing) + int(invalid)
        for passing, failing, invalid in _STATISTICS_LINE.findall(hypothesis_statistics_output)
    ]


@dataclass(frozen=True)
class FuzzRunReport:
    """What one fuzz sweep actually did, independent of the pytest process's own exit code."""

    total_examples: int
    property_count: int
    duration_seconds: float

    @property
    def is_credible(self) -> bool:
        """False for a run too small to be the real budgeted sweep, whatever its exit code."""
        return self.total_examples >= _MINIMUM_TOTAL_EXAMPLES

    def summary(self) -> str:
        return (
            f"poe fuzz: {self.total_examples} examples across {self.property_count} properties "
            f"in {self.duration_seconds:.1f}s (floor: {_MINIMUM_TOTAL_EXAMPLES} examples)"
        )


@dataclass(frozen=True)
class AtherisRunReport:
    """What one real, time-boxed atheris run actually executed."""

    executions: int | None
    duration_seconds: float

    @property
    def is_credible(self) -> bool:
        """False for a run too short/small to be a genuine fuzz over its own time budget."""
        if self.executions is None:
            return False
        minimum = _ATHERIS_MINIMUM_EXEC_PER_SECOND * self.duration_seconds
        return self.executions >= minimum

    def summary(self) -> str:
        return (
            f"poe fuzz (atheris, target 1): {self.executions} executions in "
            f"{self.duration_seconds:.1f}s (floor: {_ATHERIS_MINIMUM_EXEC_PER_SECOND}/s)"
        )


def run_atheris_target() -> tuple[int, AtherisRunReport]:
    """Runs the real coverage-guided harness for `_ATHERIS_BUDGET_SECONDS` and reports what it
    actually executed. A genuine crash makes libFuzzer exit non-zero, which propagates as this
    run's own failure -- exactly as a real finding should."""
    start = time.monotonic()
    result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        [
            sys.executable,
            str(_ATHERIS_TARGET),
            f"-max_total_time={_ATHERIS_BUDGET_SECONDS}",
            "-print_final_stats=1",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    duration = time.monotonic() - start
    combined = result.stdout + result.stderr
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode, AtherisRunReport(parse_atheris_executions(combined), duration)


def run_hypothesis_sweep() -> tuple[int, FuzzRunReport]:
    """Runs the budgeted Hypothesis sweep as a subprocess and reports what it actually executed."""
    start = time.monotonic()
    result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        [
            sys.executable,
            "-m",
            "pytest",
            *_FUZZ_TEST_PATHS,
            "-q",
            "--hypothesis-show-statistics",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "NARRATIVETRACE_FUZZ": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    duration = time.monotonic() - start
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    counts = parse_example_counts(result.stdout)
    return result.returncode, FuzzRunReport(sum(counts), len(counts), duration)


def _run_atheris_stage() -> int:
    """Runs the real atheris target if importable; returns 0 immediately when it is not (the
    Hypothesis sweep is the whole story on this interpreter, not a degraded extra stage)."""
    if not module_importable("atheris"):
        return 0
    returncode, atheris_report = run_atheris_target()
    print(atheris_report.summary(), file=sys.stderr)
    if returncode != 0:
        return returncode
    if not atheris_report.is_credible:
        print(
            f"FAIL: atheris executed only {atheris_report.executions} times in "
            f"{atheris_report.duration_seconds:.1f}s — this did not do a real fuzz run.",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    print(atheris_status_message(module_importable("atheris")), file=sys.stderr)

    atheris_returncode = _run_atheris_stage()
    if atheris_returncode != 0:
        return atheris_returncode

    returncode, report = run_hypothesis_sweep()
    print(report.summary(), file=sys.stderr)

    if returncode != 0:
        return returncode
    if not report.is_credible:
        print(
            f"FAIL: only {report.total_examples} examples ran (floor "
            f"{_MINIMUM_TOTAL_EXAMPLES}) — this run did not do the real budgeted sweep; treat as "
            "a tooling/environment failure, not a clean Tier B pass.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
