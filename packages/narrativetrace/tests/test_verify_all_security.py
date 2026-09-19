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

import pytest
from scripts.verify_all_exec import CommandOutcome
from scripts.verify_all_security import (
    announce_missing_tool,
    build_sast_row,
    build_sca_row,
    build_secrets_row,
    tool_required,
)


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


class TestToolRequiredFlag:
    """Release rule 2 (2026-09-17): a tool that is not installed must say so, and the job that is
    supposed to run it makes the skip a hard failure -- `poe verify-all` used to record semgrep
    and pip-audit as an absent sibling with a note and pass the row regardless, and no scheduled
    job proved either had ever run."""

    def test_the_per_tool_flag_makes_the_tool_mandatory(self) -> None:
        assert tool_required("semgrep", {"NARRATIVETRACE_REQUIRE_SEMGREP": "1"})

    def test_a_hyphenated_tool_name_maps_onto_an_underscored_variable(self) -> None:
        assert tool_required("pip-audit", {"NARRATIVETRACE_REQUIRE_PIP_AUDIT": "1"})

    def test_the_umbrella_flag_covers_every_tool(self) -> None:
        assert tool_required("semgrep", {"NARRATIVETRACE_REQUIRE_ALL": "true"})

    def test_an_explicit_per_tool_no_overrides_the_umbrella_yes(self) -> None:
        env = {"NARRATIVETRACE_REQUIRE_ALL": "true", "NARRATIVETRACE_REQUIRE_SEMGREP": "0"}
        assert not tool_required("semgrep", env)

    def test_nothing_set_leaves_the_tool_optional(self) -> None:
        assert not tool_required("semgrep", {})

    def test_a_bare_ci_marker_is_not_enough_on_its_own(self) -> None:
        """`CI` alone must NOT make these mandatory: the per-commit CI job deliberately does not
        install the `security` group, so every push would fail on a tool it never meant to run."""
        assert not tool_required("semgrep", {"CI": "true"})


class TestRequiredToolMissingFailsTheRow:
    def _report(self, tmp_path: Path, name: str, document: dict[str, object]) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_sast_fails_when_semgrep_is_required_and_absent(self, tmp_path: Path) -> None:
        bandit_report = self._report(tmp_path, "bandit.json", {"results": []})
        row = build_sast_row(
            _outcome(exit_code=0),
            bandit_report,
            None,
            tmp_path / "absent.json",
            semgrep_required=True,
        )
        assert row.status == "failed"
        assert row.note is not None
        assert "NARRATIVETRACE_REQUIRE_SEMGREP" in row.note

    def test_sca_fails_when_pip_audit_is_required_and_absent(self, tmp_path: Path) -> None:
        osv_report = self._report(tmp_path, "osv.json", {"results": []})
        row = build_sca_row(
            _outcome(exit_code=0),
            osv_report,
            None,
            tmp_path / "absent.json",
            pip_audit_required=True,
        )
        assert row.status == "failed"
        assert row.note is not None
        assert "NARRATIVETRACE_REQUIRE_PIP_AUDIT" in row.note


class TestTheMissingToolIsAnnounced:
    def test_the_skip_line_names_the_tool_and_says_the_category_is_unchecked(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        announce_missing_tool("semgrep", required=False)
        err = capsys.readouterr().err
        assert "SKIPPED: semgrep not installed" in err
        assert "--group security" in err

    def test_the_skip_line_says_so_when_the_tool_was_required(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        announce_missing_tool("pip-audit", required=True)
        assert "SKIPPED: pip-audit not installed" in capsys.readouterr().err
