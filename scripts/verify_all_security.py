# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Row builders + runners for `secrets`, `sast`, `sca` — SCHEMA.md's "Composite categories":
`sast` (Bandit, in-gate + Semgrep, network/security-group) and `sca` (OSV-Scanner + pip-audit,
both network/security-group) are each served by more than one tool feeding one row. Per
SCHEMA.md: if at least one contributing tool genuinely ran, status reflects what running
tool(s) found; a sibling tool that was skipped is recorded in `note`, not by downgrading the
row — only when every contributing tool was skipped does the row itself become `skipped`.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from scripts.verify_all_exec import CommandOutcome, run_command, with_log_hint
from scripts.verify_all_schema import CategoryResult, Status

_TRUTHY = frozenset({"1", "true", "yes"})


def tool_required(tool: str, env: Mapping[str, str] | None = None) -> bool:
    """Whether a missing ``tool`` FAILS its row rather than degrading to a sibling-skip note.

    ``NARRATIVETRACE_REQUIRE_<TOOL>`` (``pip-audit`` -> ``PIP_AUDIT``) answers for one tool and
    wins outright, so a job can demand one and excuse another; otherwise the umbrella
    ``NARRATIVETRACE_REQUIRE_ALL=true`` (``scripts/run_security_tool.py``'s own flag) covers
    every tool. A bare ``CI`` marker deliberately does NOT — unlike `run_security_tool`, whose
    tools are fetchable binaries, semgrep and pip-audit live in the ``security`` dependency group
    that the per-commit CI job does not install, so treating CI as "required" would fail every
    push over a tool that job never meant to run.
    """
    environ = os.environ if env is None else env
    per_tool = environ.get(f"NARRATIVETRACE_REQUIRE_{tool.upper().replace('-', '_')}", "").strip()
    if per_tool:
        return per_tool.lower() in _TRUTHY
    return environ.get("NARRATIVETRACE_REQUIRE_ALL", "").strip().lower() == "true"


def announce_missing_tool(tool: str, required: bool) -> None:
    """Prints the unmistakable ``SKIPPED: <tool> not installed`` line release rule 2 demands.

    A tool that quietly contributes nothing is how a scanner gracefully skipped for a project's
    entire life (the .NET first release). This runs whether or not the tool is required — the flag
    decides the row's status, never whether the absence is visible.
    """
    consequence = (
        f"the row FAILS (NARRATIVETRACE_REQUIRE_{tool.upper().replace('-', '_')})"
        if required
        else "this category is NOT clean, it is unchecked by this tool"
    )
    print(
        f"SKIPPED: {tool} not installed — {consequence}. "
        "`uv sync --all-packages --group security` installs it.",
        file=sys.stderr,
    )


def _binary_was_skipped(outcome: CommandOutcome) -> bool:
    """`scripts/run_security_tool.py`'s own tell for "the binary could not be resolved, so this
    warned and exited 0 instead of running the tool at all" — `decide_missing_binary`'s message
    always contains `SKIPPED` on the local (non-CI) path this run takes; a real run that found
    something exits non-zero instead, and a clean real run exits 0 with no such text."""
    return outcome.exit_code == 0 and "SKIPPED" in outcome.output


# ------------------------------------------------------------------------------------- secrets


def run_gitleaks(repo_root: Path, log_dir: Path) -> tuple[CommandOutcome, Path]:
    report_path = log_dir / "secrets-gitleaks.json"
    outcome = run_command(
        [
            "python",
            "scripts/run_security_tool.py",
            "gitleaks",
            "detect",
            "--source",
            ".",
            "--redact",
            "--no-banner",
            "-f",
            "json",
            "-r",
            str(report_path),
        ],
        log_dir / "secrets.log",
        cwd=repo_root,
    )
    return outcome, report_path


def _findings_count(report_path: Path) -> int | None:
    try:
        return len(json.loads(report_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def build_secrets_row(outcome: CommandOutcome, report_path: Path) -> CategoryResult:
    skipped = _binary_was_skipped(outcome)
    status: Status = "skipped" if skipped else ("passed" if outcome.exit_code == 0 else "failed")
    findings = None if skipped else _findings_count(report_path)
    metrics: dict[str, float | int] = {} if findings is None else {"findings": findings}
    note = "gitleaks binary not resolved (not on PATH, not fetchable)" if skipped else None
    return CategoryResult(
        category="secrets",
        tool="gitleaks (full git history)",
        status=status,
        metrics=metrics,
        duration_seconds=outcome.seconds,
        note=with_log_hint(note, outcome, status),
    )


# --------------------------------------------------------------------------------------- sast


def run_bandit(repo_root: Path, log_dir: Path) -> tuple[CommandOutcome, Path]:
    report_path = log_dir / "sast-bandit.json"
    outcome = run_command(
        [
            "bandit",
            "-c",
            "pyproject.toml",
            "-r",
            "packages",
            "examples",
            "scripts",
            "-x",
            "packages/narrativetrace/mutants,packages/narrativetrace-glossary/mutants",
            "-f",
            "json",
            "-o",
            str(report_path),
        ],
        log_dir / "sast-bandit.log",
        cwd=repo_root,
    )
    return outcome, report_path


def _bandit_findings(report_path: Path) -> int | None:
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
        return len(document["results"])
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def run_semgrep(repo_root: Path, log_dir: Path) -> tuple[CommandOutcome | None, Path]:
    """`None` outcome means semgrep is not on PATH — a sibling-tool skip, not a row-level one,
    announced on stderr and failed outright when this context requires semgrep."""
    if shutil.which("semgrep") is None:
        announce_missing_tool("semgrep", tool_required("semgrep"))
        return None, log_dir / "sast-semgrep.json"
    report_path = log_dir / "sast-semgrep.json"
    outcome = run_command(
        [
            "semgrep",
            "--config=p/security-audit",
            "--config=p/secrets",
            "--metrics=off",
            "--json",
            f"--output={report_path}",
            "packages",
            "examples",
            "scripts",
        ],
        log_dir / "sast-semgrep.log",
        cwd=repo_root,
    )
    return outcome, report_path


def _semgrep_findings(report_path: Path) -> tuple[int | None, list[str]]:
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
        results = document["results"]
    except (OSError, json.JSONDecodeError, KeyError):
        return None, []
    locations = [f"{r['check_id']} ({r['path']}:{r['start']['line']})" for r in results]
    return len(results), locations


def _missing_tool_note(tool: str, required: bool, otherwise: str) -> str:
    if not required:
        return otherwise
    variable = f"NARRATIVETRACE_REQUIRE_{tool.upper().replace('-', '_')}"
    return f"{tool} not installed, and {variable} demands it here — nothing was scanned by it"


def _sast_note(
    semgrep_outcome: CommandOutcome | None, semgrep_locations: list[str], semgrep_required: bool
) -> str | None:
    if semgrep_outcome is None:
        return _missing_tool_note(
            "semgrep",
            semgrep_required,
            "semgrep not on PATH; only Bandit ran (not wired into uv sync --group security here)",
        )
    if semgrep_locations:
        return f"semgrep findings: {'; '.join(semgrep_locations)}"
    return None


def build_sast_row(
    bandit_outcome: CommandOutcome,
    bandit_report: Path,
    semgrep_outcome: CommandOutcome | None,
    semgrep_report: Path,
    *,
    semgrep_required: bool | None = None,
) -> CategoryResult:
    required = tool_required("semgrep") if semgrep_required is None else semgrep_required
    bandit_findings = _bandit_findings(bandit_report)
    semgrep_findings, semgrep_locations = (
        (None, []) if semgrep_outcome is None else _semgrep_findings(semgrep_report)
    )
    bandit_failed = bandit_outcome.exit_code != 0 or (bandit_findings or 0) > 0
    semgrep_failed = (semgrep_findings or 0) > 0 or (semgrep_outcome is None and required)
    status: Status = "failed" if bandit_failed or semgrep_failed else "passed"
    metrics: dict[str, float | int] = {}
    if bandit_findings is not None:
        metrics["findings"] = bandit_findings
    if semgrep_findings is not None:
        metrics["findings_semgrep"] = semgrep_findings
    duration = bandit_outcome.seconds + (semgrep_outcome.seconds if semgrep_outcome else 0.0)
    tool = "Bandit (in-gate) + Semgrep (p/security-audit + p/secrets, security group)"
    note = _sast_note(semgrep_outcome, semgrep_locations, required)
    return CategoryResult(
        category="sast",
        tool=tool,
        status=status,
        metrics=metrics,
        duration_seconds=duration,
        note=with_log_hint(note, bandit_outcome, status),
    )


# ---------------------------------------------------------------------------------------- sca


def run_osv_scanner(repo_root: Path, log_dir: Path) -> tuple[CommandOutcome, Path]:
    report_path = log_dir / "sca-osv.json"
    outcome = run_command(
        [
            "python",
            "scripts/run_security_tool.py",
            "osv-scanner",
            "scan",
            "source",
            "-r",
            ".",
            "--format",
            "json",
            "--output-file",
            str(report_path),
        ],
        log_dir / "sca-osv.log",
        cwd=repo_root,
    )
    return outcome, report_path


def _osv_findings(report_path: Path) -> int | None:
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
        return len(document["results"])
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def run_pip_audit(repo_root: Path, log_dir: Path) -> tuple[CommandOutcome | None, Path]:
    """`None` outcome means pip-audit is not on PATH — announced on stderr, and failed outright
    when this context requires it (see :func:`tool_required`)."""
    if shutil.which("pip-audit") is None:
        announce_missing_tool("pip-audit", tool_required("pip-audit"))
        return None, log_dir / "sca-pip-audit.json"
    report_path = log_dir / "sca-pip-audit.json"
    outcome = run_command(
        ["pip-audit", "-f", "json", "-o", str(report_path)],
        log_dir / "sca-pip-audit.log",
        cwd=repo_root,
    )
    return outcome, report_path


def _pip_audit_findings(report_path: Path) -> int | None:
    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
        return sum(len(dep["vulns"]) for dep in document["dependencies"])
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def _sca_status(
    osv_skipped: bool,
    osv_failed: bool,
    pip_failed: bool,
    pip_audit_outcome: CommandOutcome | None,
) -> Status:
    # A real failure outranks "every contributing tool was skipped": a tool the caller REQUIRED
    # and did not get is a failure, never a skip, however quiet its sibling was.
    if osv_failed or pip_failed:
        return "failed"
    return "skipped" if osv_skipped and pip_audit_outcome is None else "passed"


def _sca_metrics(osv_findings: int | None, pip_findings: int | None) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}
    if osv_findings is not None:
        metrics["findings"] = osv_findings
    if pip_findings is not None:
        metrics["findings_pip_audit"] = pip_findings
    return metrics


def _sca_note(
    osv_skipped: bool, pip_audit_outcome: CommandOutcome | None, pip_audit_required: bool
) -> str | None:
    notes = []
    if osv_skipped:
        notes.append("osv-scanner binary not resolved (not on PATH, not fetchable)")
    if pip_audit_outcome is None:
        notes.append(
            _missing_tool_note(
                "pip-audit",
                pip_audit_required,
                "pip-audit not on PATH (uv sync --group security installs it)",
            )
        )
    return "; ".join(notes) if notes else None


def build_sca_row(
    osv_outcome: CommandOutcome,
    osv_report: Path,
    pip_audit_outcome: CommandOutcome | None,
    pip_audit_report: Path,
    *,
    pip_audit_required: bool | None = None,
) -> CategoryResult:
    required = tool_required("pip-audit") if pip_audit_required is None else pip_audit_required
    osv_skipped = _binary_was_skipped(osv_outcome)
    osv_findings = None if osv_skipped else _osv_findings(osv_report)
    pip_findings = None if pip_audit_outcome is None else _pip_audit_findings(pip_audit_report)

    osv_failed = not osv_skipped and ((osv_findings or 0) > 0 or osv_outcome.exit_code != 0)
    pip_failed = (pip_audit_outcome is None and required) or (
        pip_audit_outcome is not None
        and ((pip_findings or 0) > 0 or pip_audit_outcome.exit_code != 0)
    )
    status = _sca_status(osv_skipped, osv_failed, pip_failed, pip_audit_outcome)
    duration = osv_outcome.seconds + (pip_audit_outcome.seconds if pip_audit_outcome else 0.0)
    note = _sca_note(osv_skipped, pip_audit_outcome, required)
    return CategoryResult(
        category="sca",
        tool="OSV-Scanner (source scan over uv.lock) + pip-audit (installed environment)",
        status=status,
        metrics=_sca_metrics(osv_findings, pip_findings),
        duration_seconds=duration,
        note=with_log_hint(note, osv_outcome, status),
    )
