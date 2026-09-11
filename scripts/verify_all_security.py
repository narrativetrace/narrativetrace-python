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
import shutil
from pathlib import Path

from scripts.verify_all_exec import CommandOutcome, run_command, with_log_hint
from scripts.verify_all_schema import CategoryResult, Status


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
    """`None` outcome means semgrep is not on PATH — a sibling-tool skip, not a row-level one."""
    if shutil.which("semgrep") is None:
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


def _sast_note(semgrep_outcome: CommandOutcome | None, semgrep_locations: list[str]) -> str | None:
    if semgrep_outcome is None:
        return "semgrep not on PATH; only Bandit ran (not wired into uv sync --group security here)"
    if semgrep_locations:
        return f"semgrep findings: {'; '.join(semgrep_locations)}"
    return None


def build_sast_row(
    bandit_outcome: CommandOutcome,
    bandit_report: Path,
    semgrep_outcome: CommandOutcome | None,
    semgrep_report: Path,
) -> CategoryResult:
    bandit_findings = _bandit_findings(bandit_report)
    semgrep_findings, semgrep_locations = (
        (None, []) if semgrep_outcome is None else _semgrep_findings(semgrep_report)
    )
    bandit_failed = bandit_outcome.exit_code != 0 or (bandit_findings or 0) > 0
    semgrep_failed = (semgrep_findings or 0) > 0
    status: Status = "failed" if bandit_failed or semgrep_failed else "passed"
    metrics: dict[str, float | int] = {}
    if bandit_findings is not None:
        metrics["findings"] = bandit_findings
    if semgrep_findings is not None:
        metrics["findings_semgrep"] = semgrep_findings
    duration = bandit_outcome.seconds + (semgrep_outcome.seconds if semgrep_outcome else 0.0)
    tool = "Bandit (in-gate) + Semgrep (p/security-audit + p/secrets, security group)"
    note = _sast_note(semgrep_outcome, semgrep_locations)
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
    if shutil.which("pip-audit") is None:
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
    if osv_skipped and pip_audit_outcome is None:
        return "skipped"
    return "failed" if osv_failed or pip_failed else "passed"


def _sca_metrics(osv_findings: int | None, pip_findings: int | None) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}
    if osv_findings is not None:
        metrics["findings"] = osv_findings
    if pip_findings is not None:
        metrics["findings_pip_audit"] = pip_findings
    return metrics


def _sca_note(osv_skipped: bool, pip_audit_outcome: CommandOutcome | None) -> str | None:
    notes = []
    if osv_skipped:
        notes.append("osv-scanner binary not resolved (not on PATH, not fetchable)")
    if pip_audit_outcome is None:
        notes.append("pip-audit not on PATH (uv sync --group security installs it)")
    return "; ".join(notes) if notes else None


def build_sca_row(
    osv_outcome: CommandOutcome,
    osv_report: Path,
    pip_audit_outcome: CommandOutcome | None,
    pip_audit_report: Path,
) -> CategoryResult:
    osv_skipped = _binary_was_skipped(osv_outcome)
    osv_findings = None if osv_skipped else _osv_findings(osv_report)
    pip_findings = None if pip_audit_outcome is None else _pip_audit_findings(pip_audit_report)

    osv_failed = not osv_skipped and ((osv_findings or 0) > 0 or osv_outcome.exit_code != 0)
    pip_failed = pip_audit_outcome is not None and (
        (pip_findings or 0) > 0 or pip_audit_outcome.exit_code != 0
    )
    status = _sca_status(osv_skipped, osv_failed, pip_failed, pip_audit_outcome)
    duration = osv_outcome.seconds + (pip_audit_outcome.seconds if pip_audit_outcome else 0.0)
    note = _sca_note(osv_skipped, pip_audit_outcome)
    return CategoryResult(
        category="sca",
        tool="OSV-Scanner (source scan over uv.lock) + pip-audit (installed environment)",
        status=status,
        metrics=_sca_metrics(osv_findings, pip_findings),
        duration_seconds=duration,
        note=with_log_hint(note, osv_outcome, status),
    )
