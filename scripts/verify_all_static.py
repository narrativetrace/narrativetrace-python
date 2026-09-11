# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Row builders + runners for the static-analysis categories that need no test framework:
`format`, `lint`, `complexity`, `types`, `translation`, `clarity`.

Each `run_*` function is one real invocation (or, for `complexity`, a slice of `lint`'s own
already-parsed output — SCHEMA.md's "Derived categories" convention, 0 additional invocations);
each `build_*_row` turns that outcome into a `CategoryResult`. Every metric here is read back
from a tool's own structured output (`ruff --output-format=json`, `clarity-results.json`) or
its own console summary line — never invented, per SCHEMA.md's "Metrics that are hard to parse".
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.verify_all_exec import CommandOutcome, run_command, with_log_hint
from scripts.verify_all_schema import CategoryResult, Status

_MYPY_SUCCESS = re.compile(r"Success: no issues found in (\d+) source files?")
_MYPY_ERRORS = re.compile(r"Found (\d+) error")
_MYPY_CHECKED = re.compile(r"\(checked (\d+) source files?\)")
_TRANSLATION_UNREVIEWED = re.compile(r"(\d+) translated document\(s\) unreviewed")


# --------------------------------------------------------------------------------------- format


def run_ruff_format_check(repo_root: Path, log_dir: Path) -> CommandOutcome:
    return run_command(["ruff", "format", "--check", "."], log_dir / "format.log", cwd=repo_root)


def build_format_row(outcome: CommandOutcome, ruff_version: str) -> CategoryResult:
    status: Status = "passed" if outcome.exit_code == 0 else "failed"
    return CategoryResult(
        category="format",
        tool=f"Ruff {ruff_version} (format --check)",
        status=status,
        metrics={},
        duration_seconds=outcome.seconds,
        note=with_log_hint(
            "no structured reformat count in ruff's own console output"
            if status == "failed"
            else None,
            outcome,
            status,
        ),
    )


# ----------------------------------------------------------------------------------------- lint


def run_ruff_check_json(
    repo_root: Path, log_dir: Path
) -> tuple[CommandOutcome, list[dict[str, object]]]:
    """One real `ruff check --output-format=json` invocation — `lint` and `complexity`'s
    `PLR0915` slice both read from this same parsed list, per SCHEMA.md's "Derived categories"."""
    outcome = run_command(
        ["ruff", "check", "--output-format=json", "."], log_dir / "lint.log", cwd=repo_root
    )
    try:
        violations: list[dict[str, object]] = json.loads(outcome.output)
    except json.JSONDecodeError:
        violations = []
    return outcome, violations


def build_lint_row(
    outcome: CommandOutcome, violations: list[dict[str, object]], ruff_version: str
) -> CategoryResult:
    status: Status = "passed" if outcome.exit_code == 0 else "failed"
    return CategoryResult(
        category="lint",
        tool=f"Ruff {ruff_version} (check)",
        status=status,
        metrics={"findings": len(violations)},
        duration_seconds=outcome.seconds,
        note=with_log_hint(None, outcome, status),
    )


# ------------------------------------------------------------------------------------ complexity


def run_xenon(repo_root: Path, log_dir: Path) -> CommandOutcome:
    return run_command(
        ["xenon", "--max-absolute", "B", "--max-modules", "B", "--max-average", "A", "packages"],
        log_dir / "complexity.log",
        cwd=repo_root,
    )


def build_complexity_row(
    xenon_outcome: CommandOutcome, violations: list[dict[str, object]]
) -> CategoryResult:
    plr0915_findings = sum(1 for v in violations if v.get("code") == "PLR0915")
    xenon_clean = xenon_outcome.exit_code == 0
    status: Status = "passed" if xenon_clean and plr0915_findings == 0 else "failed"
    note = (
        "xenon's own console output carries no structured violation count when clean; "
        "findings is ruff's PLR0915 (too-many-statements) count, sliced from the lint row's "
        "own ruff JSON run — 0 additional invocations"
    )
    return CategoryResult(
        category="complexity",
        tool="xenon 0.9 (radon; max-absolute B, max-modules B, max-average A) + ruff PLR0915",
        status=status,
        metrics={"findings": plr0915_findings},
        duration_seconds=xenon_outcome.seconds,
        note=with_log_hint(note, xenon_outcome, status),
    )


# ---------------------------------------------------------------------------------------- types


def run_mypy(repo_root: Path, log_dir: Path) -> CommandOutcome:
    return run_command(["mypy"], log_dir / "types.log", cwd=repo_root)


def _mypy_findings(output: str) -> int | None:
    success = _MYPY_SUCCESS.search(output)
    if success is not None:
        return 0
    errors = _MYPY_ERRORS.search(output)
    return int(errors.group(1)) if errors is not None else None


def build_types_row(outcome: CommandOutcome, mypy_version: str) -> CategoryResult:
    status: Status = "passed" if outcome.exit_code == 0 else "failed"
    findings = _mypy_findings(outcome.output)
    metrics: dict[str, float | int] = {} if findings is None else {"findings": findings}
    checked = _MYPY_CHECKED.search(outcome.output) or _MYPY_SUCCESS.search(outcome.output)
    note = f"{checked.group(1)} source files checked" if checked else None
    return CategoryResult(
        category="types",
        tool=f"mypy {mypy_version} (--strict)",
        status=status,
        metrics=metrics,
        duration_seconds=outcome.seconds,
        note=with_log_hint(note, outcome, status),
    )


# ----------------------------------------------------------------------------------- translation


def run_translation_check(repo_root: Path, log_dir: Path) -> CommandOutcome:
    return run_command(
        ["python", "scripts/translation_check.py"], log_dir / "translation.log", cwd=repo_root
    )


def build_translation_row(outcome: CommandOutcome) -> CategoryResult:
    status: Status = "passed" if outcome.exit_code == 0 else "failed"
    unreviewed = _TRANSLATION_UNREVIEWED.search(outcome.output)
    note = (
        f"{unreviewed.group(1)} translated document(s) unreviewed (informational, not a "
        "failure — see poe translation-status); code-fence content drift is warned, never failed"
        if unreviewed
        else None
    )
    return CategoryResult(
        category="translation",
        tool="custom translation_check.py (blob-hash headers + i18n manifest)",
        status=status,
        metrics={},
        duration_seconds=outcome.seconds,
        note=with_log_hint(note, outcome, status),
    )


# --------------------------------------------------------------------------------------- clarity

_CLARITY_SOURCES = (
    "packages/narrativetrace/src",
    "packages/narrativetrace-diagrams/src",
    "packages/narrativetrace-otel/src",
    "packages/narrativetrace-asgi/src",
    "packages/narrativetrace-clarity/src",
    "packages/narrativetrace-glossary/src",
    "packages/narrativetrace-pytest/src",
    "packages/narrativetrace-structlog/src",
)


def run_clarity_scan(repo_root: Path, log_dir: Path) -> CommandOutcome:
    return run_command(
        [
            "python",
            "-m",
            "narrativetrace_glossary.clarity_scan",
            *_CLARITY_SOURCES,
            "--min-score",
            "0.5",
            "--output-dir",
            "build/narrativetrace",
            "--glossary-dir",
            ".",
        ],
        log_dir / "clarity.log",
        cwd=repo_root,
    )


def _clarity_metrics(results_path: Path) -> tuple[dict[str, float | int], int]:
    document = json.loads(results_path.read_text(encoding="utf-8"))
    scenarios = document["scenarios"]
    if not scenarios:
        return {}, 0
    high_issues = sum(1 for s in scenarios for issue in s["issues"] if issue["severity"] == "HIGH")
    average = sum(s["overallScore"] for s in scenarios) / len(scenarios)
    return {"high_issues": high_issues, "score": round(average, 2)}, len(scenarios)


def build_clarity_row(outcome: CommandOutcome, results_path: Path) -> CategoryResult:
    status: Status = "passed" if outcome.exit_code == 0 else "failed"
    try:
        metrics, scanned = _clarity_metrics(results_path)
        note = f"{scanned} class(es) scanned"
    except (OSError, KeyError, json.JSONDecodeError):
        metrics, note = {}, "clarity-results.json could not be read back"
    return CategoryResult(
        category="clarity",
        tool="narrativetrace-clarity + narrativetrace_glossary vocabulary (min-score 0.5)",
        status=status,
        metrics=metrics,
        duration_seconds=outcome.seconds,
        note=with_log_hint(note, outcome, status),
    )
