# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`poe vendor-validate` -- the seam where a VENDOR's own validator checks an artifact this
repository publishes for that vendor to read (D6, phase-4-design-2026-09-27.md, "the owner's
addition"): a REGISTRY, not one hard-coded invocation, so `npx skills` dry runs and the other
vendor tools this family cares about join as ROWS later, never as new machinery.

Belongs to the heavy/scheduled verification tier (`verify-all`'s own `vendor-validation`
category) and is never wired into `poe check`: a per-commit gate may not depend on a
third-party CLI being installed. The precondition lives HERE, in each row's own run, never as a
CI-side exclusion: an absent tool SKIPS with one line naming it and how to install it, and so
does a tool that is present but fails its own probe -- a broken install must not fail a gate
about this repository's own artifact. Every outcome is recorded under
`build/reports/vendor-validation/<tool>.status`, read back by `verify-all` rather than inferred
from an exit code a skip also leaves at zero: a skip is not a pass.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "build" / "reports" / "vendor-validation"


class VendorOutcome(Enum):
    """What one row's run amounted to. A skip is never a pass: nothing was validated."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class VendorCheck:
    """One vendor's own validator for one artifact this repository publishes, as DATA.

    tool: the executable, looked up on PATH by this name.
    probe: argv (after tool) that proves the tool answers at all -- a tool present but unusable
        must skip like an absent one, never fail a gate about this repository's own artifact.
    validate: argv (after tool) that performs the validation; the staged artifact root is
        appended as the last argument.
    artifact: repo-relative path of what this row validates, for the log and the report.
    staged_paths: repo-relative paths the validation needs staged -- the artifact and whatever
        it points at (a marketplace file is only valid together with the plugin directory its
        entry names), so the tool sees the same tree a consumer's clone would.
    install_hint: one line telling a reader how to make `tool` available.
    """

    tool: str
    probe: tuple[str, ...]
    validate: tuple[str, ...]
    artifact: str
    staged_paths: tuple[str, ...]
    install_hint: str


@dataclass(frozen=True)
class VendorCheckResult:
    """One row's result: what ran, what it decided, and everything it printed."""

    tool: str
    artifact: str
    outcome: VendorOutcome
    message: str
    output: str


# Every vendor validation this repository knows how to run. One row today: the plugin
# marketplace file, validated by the agent CLI that reads it.
CHECKS: tuple[VendorCheck, ...] = (
    VendorCheck(
        tool="claude",
        probe=("--version",),
        validate=("plugin", "validate"),
        artifact=".claude-plugin/marketplace.json",
        staged_paths=(".claude-plugin", ".claude/skills"),
        install_hint="install the agent CLI (npm i -g @anthropic-ai/claude-code) and re-run",
    ),
)


def executable_on_path(name: str, path_value: str | None) -> str | None:
    """The first executable named `name` on `path_value` (the real environment's own `PATH`
    when `None`), or `None` when nothing there can run."""
    return shutil.which(name, path=path_value)


def _execute(executable: str, args: tuple[str, ...], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(  # nosec B603 # fixed argv (the registry's own data plus a resolved
        # executable path), no shell, no untrusted input
        [executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def validate(
    check: VendorCheck, artifact_root: Path, path_value: str | None = None
) -> VendorCheckResult:
    """Runs one row against `artifact_root` -- the staged tree holding the artifact -- resolving
    the tool on `path_value` (the real environment's own `PATH` when `None`).

    Three outcomes, in this order: the tool is absent or does not answer its probe -> SKIPPED
    with a one-line reason naming it and `check.install_hint`; the validator exits zero ->
    PASSED; anything else -> FAILED, carrying everything the validator printed.
    """
    executable = executable_on_path(check.tool, path_value)
    if executable is None:
        return _skipped(check, "not found on PATH")
    probe_exit, _ = _execute(executable, check.probe, artifact_root)
    if probe_exit != 0:
        return _skipped(
            check, f"found at {executable} but its own probe failed (exit {probe_exit})"
        )
    exit_code, output = _execute(executable, (*check.validate, str(artifact_root)), artifact_root)
    if exit_code == 0:
        return VendorCheckResult(
            check.tool, check.artifact, VendorOutcome.PASSED, f"validated {check.artifact}", output
        )
    return VendorCheckResult(
        check.tool,
        check.artifact,
        VendorOutcome.FAILED,
        f"{check.tool} rejected {check.artifact} (exit {exit_code})",
        output,
    )


def _skipped(check: VendorCheck, reason: str) -> VendorCheckResult:
    """SKIPPED, with the one line a reader needs: which tool, why, and how to make it
    available."""
    return VendorCheckResult(
        check.tool,
        check.artifact,
        VendorOutcome.SKIPPED,
        f"{check.tool} {reason} — {check.artifact} was NOT validated; {check.install_hint}",
        "",
    )


def aggregate(results: Sequence[VendorCheckResult]) -> VendorOutcome:
    """The whole run's verdict: FAILED when any row failed, PASSED when at least one row
    genuinely ran clean, SKIPPED otherwise -- including when there are no rows at all. A run
    where every vendor CLI was absent validated nothing, and must never read as a pass."""
    if any(result.outcome is VendorOutcome.FAILED for result in results):
        return VendorOutcome.FAILED
    if any(result.outcome is VendorOutcome.PASSED for result in results):
        return VendorOutcome.PASSED
    return VendorOutcome.SKIPPED


def _status_file(reports_dir: Path, tool: str) -> Path:
    return reports_dir / f"{tool}.status"


def record(reports_dir: Path, result: VendorCheckResult) -> None:
    """Records one row's outcome under `reports_dir`, so "validated" and "never validated" stay
    distinguishable after the fact -- by a person and by `verify-all`, which reads these back
    rather than inferring a status from an exit code a skip also leaves at zero."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    _status_file(reports_dir, result.tool).write_text(
        f"{result.outcome.value}: {result.message}\n", encoding="utf-8"
    )


def recorded_status(reports_dir: Path, tool: str) -> str:
    """What `tool`'s last recorded run said, or `"never-ran"` when it has no record at all."""
    status_file = _status_file(reports_dir, tool)
    return status_file.read_text(encoding="utf-8").strip() if status_file.is_file() else "never-ran"


def _run_or_raise(cwd: Path, command: list[str]) -> None:
    result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        command, cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command)} failed (exit {result.returncode}): {result.stdout}{result.stderr}"
        )


def stage_from_head(repo_root: Path, paths: tuple[str, ...], into: Path) -> None:
    """Stages `paths` out of `HEAD` into `into`: `git archive`, never the working tree, so what a
    vendor validates is what a publish would ship -- uncommitted edits are invisible here exactly
    as they are to the publish script's own staging.

    Raises `ValueError` when `paths` is empty: `git archive <tree> --` with nothing after `--`
    is not an empty pathspec in git's own semantics -- it archives the ENTIRE tree, so a caller
    passing `()` by mistake would silently stage the whole repository instead of nothing, far
    more than any real `VendorCheck.staged_paths` is ever meant to name.

    Raises `RuntimeError` when git or tar cannot produce the tree; a validation gate that
    silently validated nothing would be worse than one that stops.
    """
    if not paths:
        raise ValueError("stage_from_head: paths must not be empty (would archive the entire repo)")
    into.mkdir(parents=True, exist_ok=True)
    archive = into / "head.tar"
    _run_or_raise(
        repo_root, ["git", "archive", "--format=tar", "-o", str(archive), "HEAD", "--", *paths]
    )
    _run_or_raise(into, ["tar", "-xf", str(archive), "-C", str(into)])
    archive.unlink()


def main() -> int:
    results: list[VendorCheckResult] = []
    for check in CHECKS:
        stage = Path(tempfile.mkdtemp(prefix="vendor-validate-"))
        try:
            stage_from_head(REPO_ROOT, check.staged_paths, stage)
            result = validate(check, stage)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        record(REPORTS_DIR, result)
        print(f"vendor-validate: {check.tool} {result.outcome.value} — {result.message}")
        results.append(result)

    outcome = aggregate(results)
    if outcome is VendorOutcome.FAILED:
        print(
            "vendor-validate: a vendor rejected an artifact this repository publishes — "
            "see the output above"
        )
        return 1
    if outcome is VendorOutcome.SKIPPED:
        print(
            "vendor-validate: every row SKIPPED — nothing was validated. A skip is not a pass; "
            "install the missing tool(s) named above and re-run for a real result."
        )
        return 0
    passed = sum(1 for result in results if result.outcome is VendorOutcome.PASSED)
    print(f"vendor-validate: {passed}/{len(results)} rows passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
