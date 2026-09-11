# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Subprocess/host glue shared by every `poe verify-all` category runner
(`scripts/verify_all_exec.py`). `run_command`'s real subprocess execution is exercised by
actually running `poe verify-all`, not here — mirrors `test_mutation_gate.py`'s own split.
"""

from __future__ import annotations

from pathlib import Path

from scripts.verify_all_exec import (
    CommandOutcome,
    host_descriptor,
    load_average_1min,
    repo_version,
    run_command,
    short_commit,
    tool_version,
    with_log_hint,
)


def _outcome(log_file: Path, exit_code: int = 0) -> CommandOutcome:
    return CommandOutcome(exit_code=exit_code, output="", seconds=1.0, log_file=log_file)


class TestWithLogHint:
    def test_a_passed_row_carries_the_note_unchanged(self, tmp_path: Path) -> None:
        note = with_log_hint("some note", _outcome(tmp_path / "x.log"), "passed")
        assert note == "some note"

    def test_a_passed_row_with_no_note_stays_none(self, tmp_path: Path) -> None:
        assert with_log_hint(None, _outcome(tmp_path / "x.log"), "passed") is None

    def test_a_failed_row_appends_the_log_path(self, tmp_path: Path) -> None:
        log = tmp_path / "x.log"
        note = with_log_hint(None, _outcome(log, exit_code=1), "failed")
        assert note == f"full output: {log}"

    def test_a_failed_row_with_an_existing_note_appends_after_it(self, tmp_path: Path) -> None:
        log = tmp_path / "x.log"
        note = with_log_hint("why it failed", _outcome(log, exit_code=1), "failed")
        assert note == f"why it failed; full output: {log}"

    def test_a_skipped_row_also_gets_the_log_hint(self, tmp_path: Path) -> None:
        log = tmp_path / "x.log"
        note = with_log_hint(None, _outcome(log), "skipped")
        assert note == f"full output: {log}"


class TestRunCommand:
    def test_captures_exit_code_output_and_writes_the_log(self, tmp_path: Path) -> None:
        log = tmp_path / "out" / "run.log"
        outcome = run_command(["python", "-c", "print('hi')"], log)

        assert outcome.exit_code == 0
        assert "hi" in outcome.output
        assert log.read_text(encoding="utf-8") == outcome.output

    def test_a_nonzero_exit_is_captured_not_raised(self, tmp_path: Path) -> None:
        outcome = run_command(["python", "-c", "import sys; sys.exit(3)"], tmp_path / "run.log")
        assert outcome.exit_code == 3


class TestHostDescriptor:
    def test_is_hostname_dash_arch(self) -> None:
        descriptor = host_descriptor()
        assert "-" in descriptor
        assert len(descriptor.split("-")[-1]) > 0


class TestShortCommit:
    def test_returns_a_short_hex_hash_for_a_real_repo(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        commit = short_commit(repo_root)
        assert commit == "unknown" or all(c in "0123456789abcdef" for c in commit)

    def test_returns_unknown_for_a_directory_with_no_git_repo(self, tmp_path: Path) -> None:
        assert short_commit(tmp_path) == "unknown"


class TestRepoVersion:
    def test_reads_the_project_version_from_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
        )
        assert repo_version(tmp_path) == "1.2.3"

    def test_raises_when_no_version_is_declared(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        try:
            repo_version(tmp_path)
        except ValueError as exc:
            assert "version" in str(exc)
        else:
            raise AssertionError("expected ValueError")


class TestToolVersion:
    def test_extracts_a_version_looking_token(self) -> None:
        assert tool_version(["python", "--version"]) != "unknown"

    def test_unknown_for_a_binary_that_does_not_exist(self) -> None:
        assert tool_version(["definitely-not-a-real-binary-xyz"]) == "unknown"


class TestLoadAverage1Min:
    def test_returns_a_non_negative_float(self) -> None:
        assert load_average_1min() >= 0.0
