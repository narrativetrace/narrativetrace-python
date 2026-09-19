# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/tree_writes_guard.py`: fails a wrapped command that left anything behind in the
tracked working tree, even when the command's own exit code is zero.

`new_working_tree_entries`/`report_lines` are pure and covered directly; `working_tree_status`/
`run_guarded` drive a real, disposable git repository under `tmp_path` rather than mocking
`subprocess` -- the point of this module is that it answers from git's own porcelain output, so
a test that faked that output would prove nothing about the real failure mode: a command that
exits zero after rewriting a tracked page.
"""

from __future__ import annotations

import subprocess  # nosec B404 -- fixed argv fixtures, no shell, no untrusted input
import sys
from pathlib import Path

import pytest
from scripts import tree_writes_guard
from scripts.tree_writes_guard import (
    new_working_tree_entries,
    report_lines,
    run_guarded,
    working_tree_status,
)


def _run_git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # nosec B603, B607


def _init_repo(tmp_path: Path) -> Path:
    """A real git repository with one committed, tracked file -- a clean baseline for
    `working_tree_status`/`run_guarded` to answer against."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(["init", "-q"], cwd=repo)
    _run_git(["config", "user.email", "test@example.invalid"], cwd=repo)
    _run_git(["config", "user.name", "Test"], cwd=repo)
    (repo / "tracked.md").write_text("original\n", encoding="utf-8")
    _run_git(["add", "."], cwd=repo)
    _run_git(["commit", "-q", "-m", "initial"], cwd=repo)
    return repo


class TestNewWorkingTreeEntries:
    def test_sees_nothing_when_the_command_left_the_tree_as_it_found_it(self) -> None:
        assert new_working_tree_entries([], []) == []

    def test_reports_a_file_the_command_created(self) -> None:
        assert new_working_tree_entries([], ["?? documentation/page.md"]) == [
            "?? documentation/page.md"
        ]

    def test_reports_a_tracked_file_the_command_rewrote(self) -> None:
        assert new_working_tree_entries([], [" M documentation/guide.md"]) == [
            " M documentation/guide.md"
        ]

    def test_ignores_edits_that_were_already_there_when_the_command_started(self) -> None:
        before = [" M documentation/guide.md"]
        assert new_working_tree_entries(before, before) == []

    def test_reports_a_file_whose_state_changed_under_a_command_that_did_not_create_it(
        self,
    ) -> None:
        assert new_working_tree_entries(
            ["?? documentation/guide.md"], [" M documentation/guide.md"]
        ) == [" M documentation/guide.md"]

    def test_reports_a_rename_whose_porcelain_line_names_both_paths(self) -> None:
        assert new_working_tree_entries([], ["R  a.md -> b.md"]) == ["R  a.md -> b.md"]


class TestReportLines:
    def test_names_the_command_and_every_path_it_wrote(self) -> None:
        lines = "\n".join(report_lines("poe coverage", [" M documentation/guide.md", "?? out.txt"]))
        assert "poe coverage" in lines
        assert "documentation/guide.md" in lines
        assert "out.txt" in lines

    def test_says_what_the_failure_means_so_the_fix_is_not_commit_the_diff(self) -> None:
        lines = "\n".join(report_lines("x", ["?? a"]))
        assert "without writing" in lines


class TestWorkingTreeStatus:
    def test_a_clean_repository_reports_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        assert working_tree_status() == []

    def test_a_new_untracked_file_shows_up(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        (repo / "untracked.md").write_text("x", encoding="utf-8")
        assert working_tree_status() == ["?? untracked.md"]

    def test_git_failing_to_answer_raises_rather_than_skipping(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", tmp_path / "not-a-repo")
        with pytest.raises(RuntimeError, match="git status exited"):
            working_tree_status()


class TestRunGuarded:
    def test_a_clean_command_returns_its_own_exit_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        assert run_guarded([sys.executable, "-c", "import sys; sys.exit(3)"]) == 3

    def test_a_command_that_rewrites_a_tracked_file_fails_even_though_it_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The failure mode this guard exists for: a command asking "is a sync pending?" that
        answers by performing the sync -- exit code zero, a tracked page rewritten underneath
        it."""
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        target = repo / "tracked.md"
        script = (
            f"from pathlib import Path; "
            f"Path({str(target)!r}).write_text('rewritten\\n', encoding='utf-8')"
        )
        assert run_guarded([sys.executable, "-c", script]) == 1
        assert "tracked.md" in capsys.readouterr().err

    def test_a_command_that_creates_an_untracked_file_still_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        target = repo / "new_output.md"
        script = (
            f"from pathlib import Path; Path({str(target)!r}).write_text('x', encoding='utf-8')"
        )
        assert run_guarded([sys.executable, "-c", script]) == 1

    def test_no_argv_is_a_usage_error_not_a_silent_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        assert run_guarded([]) == 1


class TestMain:
    def test_wraps_sys_argv_and_returns_run_guarded_s_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: list[list[str]] = []

        def _fake_run_guarded(argv: list[str]) -> int:
            recorded.append(argv)
            return 0

        monkeypatch.setattr(tree_writes_guard, "run_guarded", _fake_run_guarded)
        monkeypatch.setattr(sys, "argv", ["tree_writes_guard.py", "pytest", "-q"])

        assert tree_writes_guard.main() == 0
        assert recorded == [["pytest", "-q"]]
