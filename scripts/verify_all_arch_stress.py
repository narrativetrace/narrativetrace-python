# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Row builders + runners for `architecture` (import-linter) and the two concurrency-stress
categories (`stress-short`/`stress-long`, `poe stress-quick`/`poe stress` — quick/seeded vs
long/randomised sweep per `documentation/concurrency-stress.md`). Real, separate invocations —
none of these three is sliced from the main test sweep.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from scripts.verify_all_exec import CommandOutcome, run_command, with_log_hint
from scripts.verify_all_schema import CategoryResult, Status
from scripts.verify_all_testrun import all_green, parse_junit, summarize

_CONTRACTS_LINE = re.compile(r"Contracts:\s*(\d+)\s*kept,\s*(\d+)\s*broken")
_STRESS_PATHS = (
    "packages/narrativetrace/tests/test_pipeline_stress.py",
    "packages/narrativetrace/tests/test_context_stress.py",
)

# --------------------------------------------------------------------------------- architecture


def run_lint_imports(repo_root: Path, log_dir: Path) -> CommandOutcome:
    return run_command(["lint-imports"], log_dir / "architecture.log", cwd=repo_root)


def build_architecture_row(outcome: CommandOutcome) -> CategoryResult:
    match = _CONTRACTS_LINE.search(outcome.output)
    status: Status
    if match is None:
        status = "passed" if outcome.exit_code == 0 else "failed"
        metrics: dict[str, float | int] = {}
        note = "import-linter's console output had no parseable 'Contracts: N kept, M broken' line"
    else:
        kept, broken = int(match.group(1)), int(match.group(2))
        status = "passed" if broken == 0 else "failed"
        metrics = {"contracts_kept": kept, "contracts_broken": broken}
        note = None
    return CategoryResult(
        category="architecture",
        tool="import-linter (lint-imports, layered package-dependency contract)",
        status=status,
        metrics=metrics,
        duration_seconds=outcome.seconds,
        note=with_log_hint(note, outcome, status),
    )


# ----------------------------------------------------------------------------------- stress rows


def _run_stress(
    repo_root: Path, log_dir: Path, junit_name: str, long: bool
) -> tuple[CommandOutcome, Path]:
    junit_path = log_dir / junit_name
    env = {**os.environ, "NARRATIVETRACE_STRESS_LONG": "1"} if long else None
    outcome = run_command(
        ["pytest", "-m", "stress", *_STRESS_PATHS, f"--junitxml={junit_path}", "-q"],
        log_dir / junit_name.replace(".xml", ".log"),
        cwd=repo_root,
        env=env,
    )
    return outcome, junit_path


def run_stress_short(repo_root: Path, log_dir: Path) -> tuple[CommandOutcome, Path]:
    return _run_stress(repo_root, log_dir, "stress-short.xml", long=False)


def run_stress_long(repo_root: Path, log_dir: Path) -> tuple[CommandOutcome, Path]:
    return _run_stress(repo_root, log_dir, "stress-long.xml", long=True)


def _build_stress_row(
    category: str, tool: str, outcome: CommandOutcome, junit_path: Path
) -> CategoryResult:
    try:
        entries, suite_seconds = parse_junit(junit_path)
    except (OSError, KeyError, ValueError):
        entries, suite_seconds = (), outcome.seconds
    status: Status = "passed" if all_green(entries) and outcome.exit_code == 0 else "failed"
    return CategoryResult(
        category=category,
        tool=tool,
        status=status,
        metrics=dict(summarize(entries)) if entries else {},
        duration_seconds=suite_seconds or outcome.seconds,
        note=with_log_hint(None, outcome, status),
    )


def build_stress_short_row(outcome: CommandOutcome, junit_path: Path) -> CategoryResult:
    tool = "pytest -m stress (quick/seeded mode, fixed repetition count)"
    return _build_stress_row("stress-short", tool, outcome, junit_path)


def build_stress_long_row(outcome: CommandOutcome, junit_path: Path) -> CategoryResult:
    tool = "pytest -m stress (NARRATIVETRACE_STRESS_LONG=1, long/randomised sweep)"
    return _build_stress_row("stress-long", tool, outcome, junit_path)
