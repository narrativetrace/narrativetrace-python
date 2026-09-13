# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders a :class:`~narrativetrace.doctor.types.DoctorReport` as human text or JSON."""

from __future__ import annotations

import dataclasses
import json

from narrativetrace.doctor.types import DoctorReport, Finding


def _render_finding(finding: Finding) -> list[str]:
    tag = "FAIL" if finding.status == "fail" else "PASS"
    lines = [f"[{tag}] {finding.id} — {finding.message}"]
    if finding.status == "fail":
        lines.append(f"  fix:  {finding.fix}")
        lines.append(f"  docs: {finding.doc_url}")
    lines.append("")
    return lines


def render_human(report: DoctorReport) -> str:
    """Human-readable default output: one block per finding, worst-first (failures before
    passes)."""
    failing = [finding for finding in report.findings if finding.status == "fail"]
    passing = [finding for finding in report.findings if finding.status == "pass"]
    header = f"narrativetrace doctor — {len(report.findings)} check(s), {len(failing)} finding(s)"
    summary = (
        "All checks passed."
        if not failing
        else f"{len(failing)} finding(s). Exit code {report.exit_code}."
    )
    body: list[str] = []
    for finding in [*failing, *passing]:
        body.extend(_render_finding(finding))
    return "\n".join([header, "", *body, summary])


def render_json(report: DoctorReport) -> str:
    """Machine-readable ``--json`` output: the report verbatim, stable field names."""
    payload = {
        "findings": [dataclasses.asdict(finding) for finding in report.findings],
        "exit_code": report.exit_code,
    }
    return json.dumps(payload, indent=2)
