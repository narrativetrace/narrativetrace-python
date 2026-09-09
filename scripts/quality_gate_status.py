# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Skip-vs-clean status recording for the pre-commit hook's formatter/linter checks.

The pre-commit hook (`.githooks/pre-commit`) degrades gracefully when ruff can't run locally —
by design, a missing toolchain must never block a commit (see this repo's working conventions and
the hook's own top-of-file comment). Until now that degradation was silent: the
hook printed a warning to stderr and exited 0, with nothing recorded and no way to tell "the
formatter ran and found nothing" apart from "the formatter never ran at all" after the fact —
exactly the failure class release-retrospective rule 2 pins ("a graceful-skip tool must prove it
has ever run"), already fixed for gitleaks/OSV-Scanner in `scripts/run_security_tool.py`. This
module mirrors that fix's semantics for the formatter and linter steps:

- **Locally**: a missing/broken tool still **warns** and lets the commit through — per-commit
  ergonomics are unchanged.
- **In CI (`CI` set), or under `NARRATIVETRACE_QUALITY_REQUIRED=true`**: the same missing tool
  **fails** the check instead — a run meant to provide quality assurance must mean the check
  actually ran.
- Every outcome is recorded under `build/reports/quality-checks/<tool>.status` as `ran-clean` or
  `skipped: <reason>` (no file at all reads back as `never-ran`), so "ran clean" and "never ran"
  stay distinguishable after the fact — the same reports-directory convention
  `scripts/run_security_tool.py` uses for `build/reports/security-scans/`.

The hook calls this as a small CLI (`record-clean <tool>` / `record-skip <tool> <reason>` /
`status <tool>`); `main()`'s glue is exercised by the hook actually running, not by a test here —
mirrors `scripts/mutation_gate.py`'s own split between tested pure logic and exercised-for-real
glue.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
QUALITY_CHECK_STATUS_DIR = REPO_ROOT / "build" / "reports" / "quality-checks"


@dataclass(frozen=True)
class MissingToolDecision:
    """What the caller must do when a quality-check tool can't run: fail, or warn with `message`."""

    fail: bool
    message: str


def quality_checks_required() -> bool:
    """Whether this context demands a quality check actually ran: CI, or the explicit opt-in
    flag — same shape as `run_security_tool.security_scanners_required`, one env var per
    concern."""
    return os.environ.get("NARRATIVETRACE_QUALITY_REQUIRED") == "true" or bool(os.environ.get("CI"))


def decide_missing_tool(tool: str, required: bool) -> MissingToolDecision:
    """The decision for a `tool` that could not run, given whether checks are `required` here."""
    if required:
        return MissingToolDecision(
            fail=True,
            message=(
                f"{tool} could not run and quality checks are required in this context (CI, or "
                "NARRATIVETRACE_QUALITY_REQUIRED=true)."
            ),
        )
    return MissingToolDecision(
        fail=False,
        message=(
            f"{tool} not available — check SKIPPED. A skipped check is NOT a clean check: "
            "nothing was verified."
        ),
    )


def record_skipped(reports_dir: Path, tool: str, reason: str) -> None:
    """Records that `tool`'s check was skipped for `reason`; readable back via `quality_status`."""
    _write_status(reports_dir, tool, f"skipped: {reason}")


def record_ran_clean(reports_dir: Path, tool: str) -> None:
    """Records that `tool` actually ran and found nothing to block on; readable back via
    `quality_status`."""
    _write_status(reports_dir, tool, "ran-clean")


def quality_status(reports_dir: Path, tool: str) -> str:
    """`tool`'s most recent recorded outcome: `ran-clean`, `skipped: ...`, or `never-ran` when no
    check has recorded a status at all — three states, so silence cannot masquerade as
    coverage."""
    status_file = reports_dir / f"{tool}.status"
    return status_file.read_text(encoding="utf-8").strip() if status_file.is_file() else "never-ran"


def _write_status(reports_dir: Path, tool: str, status: str) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{tool}.status").write_text(status + "\n", encoding="utf-8")


def _usage() -> int:
    print(
        "usage: quality_gate_status.py <record-clean|record-skip|status> <tool> [reason]",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return _usage()
    command, tool, *rest = argv
    if command == "record-clean":
        record_ran_clean(QUALITY_CHECK_STATUS_DIR, tool)
        return 0
    if command == "record-skip":
        reason = rest[0] if rest else "unavailable"
        record_skipped(QUALITY_CHECK_STATUS_DIR, tool, reason)
        decision = decide_missing_tool(tool, quality_checks_required())
        print(f"warning: {decision.message}", file=sys.stderr)
        return 1 if decision.fail else 0
    if command == "status":
        print(quality_status(QUALITY_CHECK_STATUS_DIR, tool))
        return 0
    print(f"quality_gate_status.py: unknown command {command!r}", file=sys.stderr)
    return _usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
