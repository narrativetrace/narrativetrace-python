# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/vendor_validation.py` -- the seam where a VENDOR's own validator checks an artifact
this repository publishes (D6, phase-4-design-2026-09-27.md). Pure logic (the skip/pass/fail
decision, staging, aggregation, recording) is exercised here against a FAKE tool on a controlled
`PATH`, never the real `claude` CLI -- that is exercised for real by running `poe vendor-validate`
by hand once per milestone, mirroring `test_mutation_gate.py`'s own split between tested pure
logic and exercised-for-real glue.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts import vendor_validation
from scripts.vendor_validation import (
    CHECKS,
    VendorCheck,
    VendorCheckResult,
    VendorOutcome,
    aggregate,
    executable_on_path,
    record,
    recorded_status,
    stage_from_head,
    validate,
)

ROW = VendorCheck(
    tool="faketool",
    probe=("--version",),
    validate=("validate",),
    artifact="some/artifact.json",
    staged_paths=("some",),
    install_hint="put faketool on the PATH",
)


def _write_fake_tool(bin_dir: Path, script: str) -> None:
    path = bin_dir / ROW.tool
    path.write_text(script + "\n", encoding="utf-8")
    path.chmod(0o755)


def _fake_tool(bin_dir: Path, exit_code: int, output: str = "") -> None:
    _write_fake_tool(
        bin_dir,
        f'#!/bin/sh\ncase "$1" in --version) echo "faketool 1.0"; exit 0 ;; esac\n'
        f"echo '{output}'\nexit {exit_code}",
    )


class TestRegistry:
    def test_carries_one_row_today_for_the_marketplace_file(self) -> None:
        assert len(CHECKS) == 1
        row = CHECKS[0]
        assert row.tool == "claude"
        assert row.validate == ("plugin", "validate")
        assert row.artifact == ".claude-plugin/marketplace.json"
        assert row.staged_paths == (".claude-plugin", ".claude/skills")


class TestValidateSkipFailPassDecision:
    def test_an_absent_tool_skips_naming_the_tool_and_how_to_install_it(
        self, tmp_path: Path
    ) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        stage = tmp_path / "stage"
        stage.mkdir()

        result = validate(ROW, stage, str(bin_dir))

        assert result.outcome is VendorOutcome.SKIPPED
        assert "faketool" in result.message
        assert "put faketool on the PATH" in result.message

    def test_a_validator_that_exits_zero_passes(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _fake_tool(bin_dir, exit_code=0, output="Validation passed")
        stage = tmp_path / "stage"
        stage.mkdir()

        result = validate(ROW, stage, str(bin_dir))

        assert result.outcome is VendorOutcome.PASSED
        assert "Validation passed" in result.output

    def test_a_tool_that_is_present_but_fails_its_own_probe_skips_not_fails(
        self, tmp_path: Path
    ) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_fake_tool(bin_dir, "#!/bin/sh\nexit 7")
        stage = tmp_path / "stage"
        stage.mkdir()

        result = validate(ROW, stage, str(bin_dir))

        assert result.outcome is VendorOutcome.SKIPPED
        assert "probe failed" in result.message
        assert "put faketool on the PATH" in result.message

    def test_a_validator_that_exits_nonzero_fails_keeping_what_it_printed(
        self, tmp_path: Path
    ) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _fake_tool(bin_dir, exit_code=1, output="owner: Invalid input")
        stage = tmp_path / "stage"
        stage.mkdir()

        result = validate(ROW, stage, str(bin_dir))

        assert result.outcome is VendorOutcome.FAILED
        assert "owner: Invalid input" in result.output
        assert "some/artifact.json" in result.message


class TestExecutableOnPath:
    def test_finds_an_executable_file(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _fake_tool(bin_dir, exit_code=0)

        assert executable_on_path("faketool", str(bin_dir)) is not None

    def test_returns_none_when_nothing_matches(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()

        assert executable_on_path("faketool", str(bin_dir)) is None


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


class TestStageFromHead:
    def test_staging_takes_the_committed_tree_never_the_working_tree(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "--quiet")
        (repo / ".claude-plugin").mkdir()
        (repo / ".claude-plugin" / "marketplace.json").write_text("committed", encoding="utf-8")
        (repo / "untracked.txt").write_text("never staged", encoding="utf-8")
        _git(repo, "add", ".claude-plugin")
        _git(repo, "commit", "--quiet", "-m", "m")
        (repo / ".claude-plugin" / "marketplace.json").write_text(
            "edited after the commit", encoding="utf-8"
        )

        into = tmp_path / "into"
        stage_from_head(repo, (".claude-plugin",), into)

        assert (into / ".claude-plugin" / "marketplace.json").read_text(
            encoding="utf-8"
        ) == "committed"
        assert not (into / "untracked.txt").exists()

    def test_raises_when_git_archive_fails(self, tmp_path: Path) -> None:
        not_a_repo = tmp_path / "not-a-repo"
        not_a_repo.mkdir()

        try:
            stage_from_head(not_a_repo, (".claude-plugin",), tmp_path / "into")
        except RuntimeError as exc:
            assert "git archive" in str(exc)
        else:
            raise AssertionError("expected a RuntimeError")


class TestAggregate:
    @staticmethod
    def _result(outcome: VendorOutcome, tool: str = "faketool") -> VendorCheckResult:
        return VendorCheckResult(tool, "a/b.json", outcome, "message", "output")

    def test_one_failing_row_fails_the_whole_run(self) -> None:
        results = [self._result(VendorOutcome.PASSED), self._result(VendorOutcome.FAILED)]
        assert aggregate(results) is VendorOutcome.FAILED

    def test_a_run_where_one_row_passed_and_others_skipped_passes(self) -> None:
        results = [self._result(VendorOutcome.SKIPPED), self._result(VendorOutcome.PASSED)]
        assert aggregate(results) is VendorOutcome.PASSED

    def test_a_run_where_every_row_skipped_is_a_skip_never_a_pass(self) -> None:
        assert aggregate([self._result(VendorOutcome.SKIPPED)]) is VendorOutcome.SKIPPED

    def test_no_rows_at_all_is_a_skip(self) -> None:
        assert aggregate([]) is VendorOutcome.SKIPPED


class TestRecordAndRecordedStatus:
    def test_a_recorded_row_reads_back_and_an_unrecorded_tool_reads_back_as_never_ran(
        self, tmp_path: Path
    ) -> None:
        reports = tmp_path / "reports"
        record(
            reports,
            VendorCheckResult("faketool", "a/b.json", VendorOutcome.SKIPPED, "message", "output"),
        )

        assert recorded_status(reports, "faketool").startswith("skipped: ")
        assert recorded_status(reports, "othertool") == "never-ran"


class TestMain:
    """`main()` is glue over the pure functions above -- mocked at the module's own seams
    (`stage_from_head`, `validate`, `REPORTS_DIR`) rather than exercising real git/subprocess
    calls a second time; the real `claude` CLI is exercised by hand once per milestone."""

    def test_a_passing_run_prints_the_count_and_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake_result = VendorCheckResult(
            "claude", ".claude-plugin/marketplace.json", VendorOutcome.PASSED, "validated", "ok"
        )
        monkeypatch.setattr(vendor_validation, "stage_from_head", lambda *a, **k: None)
        monkeypatch.setattr(vendor_validation, "validate", lambda *a, **k: fake_result)
        monkeypatch.setattr(vendor_validation, "REPORTS_DIR", tmp_path / "reports")

        exit_code = vendor_validation.main()

        assert exit_code == 0
        assert "1/1 rows passed" in capsys.readouterr().out

    def test_a_failing_row_fails_the_whole_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake_result = VendorCheckResult("claude", "x", VendorOutcome.FAILED, "rejected", "bad")
        monkeypatch.setattr(vendor_validation, "stage_from_head", lambda *a, **k: None)
        monkeypatch.setattr(vendor_validation, "validate", lambda *a, **k: fake_result)
        monkeypatch.setattr(vendor_validation, "REPORTS_DIR", tmp_path / "reports")

        exit_code = vendor_validation.main()

        assert exit_code == 1
        assert "a vendor rejected an artifact" in capsys.readouterr().out

    def test_a_skipped_run_returns_zero_with_a_skip_is_not_a_pass_message(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake_result = VendorCheckResult("claude", "x", VendorOutcome.SKIPPED, "not found", "")
        monkeypatch.setattr(vendor_validation, "stage_from_head", lambda *a, **k: None)
        monkeypatch.setattr(vendor_validation, "validate", lambda *a, **k: fake_result)
        monkeypatch.setattr(vendor_validation, "REPORTS_DIR", tmp_path / "reports")

        exit_code = vendor_validation.main()

        assert exit_code == 0
        assert "A skip is not a pass" in capsys.readouterr().out

    def test_records_every_row(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        fake_result = VendorCheckResult(
            "claude", ".claude-plugin/marketplace.json", VendorOutcome.PASSED, "validated", "ok"
        )
        reports = tmp_path / "reports"
        monkeypatch.setattr(vendor_validation, "stage_from_head", lambda *a, **k: None)
        monkeypatch.setattr(vendor_validation, "validate", lambda *a, **k: fake_result)
        monkeypatch.setattr(vendor_validation, "REPORTS_DIR", reports)

        vendor_validation.main()

        assert recorded_status(reports, "claude").startswith("passed: ")
