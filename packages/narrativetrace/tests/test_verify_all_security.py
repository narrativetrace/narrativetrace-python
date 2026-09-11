# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Row builders for the composite security categories `secrets`/`sast`/`sca`
(`scripts/verify_all_security.py`) — SCHEMA.md's "Composite categories" rule: if at least one
contributing tool genuinely ran, status reflects what running tool(s) found; only when every
contributing tool was skipped does the row itself become `skipped`.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_all_exec import CommandOutcome
from scripts.verify_all_security import build_sast_row, build_sca_row, build_secrets_row


def _outcome(output: str = "", exit_code: int = 0) -> CommandOutcome:
    return CommandOutcome(exit_code=exit_code, output=output, seconds=1.0, log_file=Path("x.log"))


class TestBuildSecretsRow:
    def test_passed_with_zero_findings_when_the_report_is_an_empty_array(
        self, tmp_path: Path
    ) -> None:
        report = tmp_path / "secrets.json"
        report.write_text("[]", encoding="utf-8")
        row = build_secrets_row(_outcome(exit_code=0), report)
        assert row.status == "passed"
        assert row.metrics == {"findings": 0}

    def test_failed_when_gitleaks_exits_nonzero(self, tmp_path: Path) -> None:
        report = tmp_path / "secrets.json"
        report.write_text('[{"Description": "leak"}]', encoding="utf-8")
        row = build_secrets_row(_outcome(exit_code=1), report)
        assert row.status == "failed"
        assert row.metrics == {"findings": 1}

    def test_skipped_when_the_binary_could_not_be_resolved(self, tmp_path: Path) -> None:
        outcome = _outcome("warning: gitleaks not found on PATH ... scan SKIPPED.", exit_code=0)
        row = build_secrets_row(outcome, tmp_path / "missing.json")
        assert row.status == "skipped"
        assert row.metrics == {}
        assert row.note is not None


class TestBuildSastRow:
    def _report(self, tmp_path: Path, name: str, document: dict[str, object]) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_passed_when_both_tools_ran_clean(self, tmp_path: Path) -> None:
        bandit_report = self._report(tmp_path, "bandit.json", {"results": []})
        semgrep_report = self._report(tmp_path, "semgrep.json", {"results": []})
        row = build_sast_row(
            _outcome(exit_code=0), bandit_report, _outcome(exit_code=0), semgrep_report
        )
        assert row.status == "passed"
        assert row.metrics == {"findings": 0, "findings_semgrep": 0}

    def test_failed_when_semgrep_finds_something_even_though_bandit_is_clean(
        self, tmp_path: Path
    ) -> None:
        bandit_report = self._report(tmp_path, "bandit.json", {"results": []})
        semgrep_report = self._report(
            tmp_path,
            "semgrep.json",
            {"results": [{"check_id": "x.y", "path": "a.py", "start": {"line": 1}}]},
        )
        row = build_sast_row(
            _outcome(exit_code=0), bandit_report, _outcome(exit_code=0), semgrep_report
        )
        assert row.status == "failed"
        assert row.metrics == {"findings": 0, "findings_semgrep": 1}
        assert row.note is not None
        assert "x.y" in row.note

    def test_bandit_only_when_semgrep_is_not_on_path(self, tmp_path: Path) -> None:
        bandit_report = self._report(tmp_path, "bandit.json", {"results": []})
        row = build_sast_row(_outcome(exit_code=0), bandit_report, None, tmp_path / "absent.json")
        assert row.status == "passed"
        assert row.metrics == {"findings": 0}
        assert row.note is not None
        assert "semgrep not on PATH" in row.note


class TestBuildScaRow:
    def _report(self, tmp_path: Path, name: str, document: dict[str, object]) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_passed_when_both_tools_ran_clean(self, tmp_path: Path) -> None:
        osv_report = self._report(tmp_path, "osv.json", {"results": []})
        pip_report = self._report(
            tmp_path, "pip.json", {"dependencies": [{"name": "x", "vulns": []}]}
        )
        row = build_sca_row(_outcome(exit_code=0), osv_report, _outcome(exit_code=0), pip_report)
        assert row.status == "passed"
        assert row.metrics == {"findings": 0, "findings_pip_audit": 0}

    def test_failed_when_pip_audit_finds_a_vulnerability(self, tmp_path: Path) -> None:
        osv_report = self._report(tmp_path, "osv.json", {"results": []})
        pip_report = self._report(
            tmp_path, "pip.json", {"dependencies": [{"name": "x", "vulns": [{"id": "CVE-1"}]}]}
        )
        row = build_sca_row(_outcome(exit_code=0), osv_report, _outcome(exit_code=1), pip_report)
        assert row.status == "failed"
        assert row.metrics == {"findings": 0, "findings_pip_audit": 1}

    def test_skipped_only_when_both_tools_could_not_run(self, tmp_path: Path) -> None:
        osv_outcome = _outcome("warning: no osv-scanner release known ... SKIPPED.", exit_code=0)
        row = build_sca_row(
            osv_outcome, tmp_path / "missing.json", None, tmp_path / "missing2.json"
        )
        assert row.status == "skipped"
        assert row.metrics == {}

    def test_not_skipped_when_only_one_sibling_tool_is_unavailable(self, tmp_path: Path) -> None:
        osv_report = self._report(tmp_path, "osv.json", {"results": []})
        row = build_sca_row(_outcome(exit_code=0), osv_report, None, tmp_path / "missing.json")
        assert row.status == "passed"
        assert row.metrics == {"findings": 0}
        assert "pip-audit not on PATH" in (row.note or "")
