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
from typing import Any

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


def _init_no_git_scope(tmp_path: Path) -> Path:
    """A directory shaped like a `git archive` extraction of this repo -- no `.git` anywhere, one
    file inside the guard's content-snapshot scope -- the baseline for the no-`.git` fallback
    tests below."""
    repo = tmp_path / "snapshot"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "tracked.py").write_text("original\n", encoding="utf-8")
    return repo


def _init_no_git_scope_with_gitignore(tmp_path: Path) -> Path:
    """Same shape as `_init_no_git_scope`, plus a `.gitignore` -- there is no `.git` to already
    filter ignored paths out of the comparison, so the content-snapshot baseline must read
    `.gitignore` itself (a real `poe check` run leaves `.hypothesis`/`.coverage`-shaped caches
    behind under this exact scope; `cache/`/`*.log` here stand in for that without depending on
    an actual test run)."""
    repo = _init_no_git_scope(tmp_path)
    (repo / ".gitignore").write_text("cache/\n*.log\n", encoding="utf-8")
    return repo


class TestContentSnapshotRespectsGitignore:
    """No `.git` means no `git status` to have already filtered ignored paths out -- an ordinary
    `poe check` run leaves gitignored caches behind that must not read as a tree write."""

    def test_a_gitignored_directory_is_not_a_tree_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_no_git_scope_with_gitignore(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        target = repo / "scripts" / "cache" / "generated.bin"
        script = (
            f"from pathlib import Path; p = Path({str(target)!r}); "
            f"p.parent.mkdir(parents=True, exist_ok=True); p.write_text('x', encoding='utf-8')"
        )
        assert run_guarded([sys.executable, "-c", script]) == 0

    def test_a_gitignored_file_at_the_repo_root_is_not_a_tree_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_no_git_scope_with_gitignore(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        target = repo / "run.log"
        script = (
            f"from pathlib import Path; Path({str(target)!r}).write_text('x', encoding='utf-8')"
        )
        assert run_guarded([sys.executable, "-c", script]) == 0

    def test_a_non_ignored_write_is_still_caught(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_no_git_scope_with_gitignore(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        target = repo / "scripts" / "new_output.py"
        script = (
            f"from pathlib import Path; Path({str(target)!r}).write_text('x', encoding='utf-8')"
        )
        assert run_guarded([sys.executable, "-c", script]) == 1


class TestGuardMode:
    def test_a_git_checkout_uses_git(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        mode, reason = tree_writes_guard.guard_mode(repo)
        assert mode == "git"
        assert reason == ""

    def test_a_checkout_with_no_git_falls_back_to_a_content_snapshot(self, tmp_path: Path) -> None:
        repo = tmp_path / "snapshot"
        repo.mkdir()
        mode, reason = tree_writes_guard.guard_mode(repo)
        assert mode == "content snapshot"
        assert "not a git repository" in reason


class TestContentSnapshotFallback:
    """`--verify` builds the staged snapshot with `git archive` and runs `poe check` inside it --
    no `.git` anywhere in that tree, so this guard must still work there (the precedent:
    `check_no_license_headers.py`'s own non-git fallback for the same --verify shape)."""

    def test_detects_a_write_the_wrapped_command_makes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = _init_no_git_scope(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        target = repo / "scripts" / "tracked.py"
        script = (
            f"from pathlib import Path; "
            f"Path({str(target)!r}).write_text('rewritten\\n', encoding='utf-8')"
        )
        assert run_guarded([sys.executable, "-c", script]) == 1
        err = capsys.readouterr().err
        assert "scripts/tracked.py" in err
        assert (
            "tree-writes-guard: content snapshot (git refused: fatal: not a git repository" in err
        )

    def test_detects_a_new_file_the_wrapped_command_creates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_no_git_scope(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        target = repo / "scripts" / "new_output.py"
        script = (
            f"from pathlib import Path; Path({str(target)!r}).write_text('x', encoding='utf-8')"
        )
        assert run_guarded([sys.executable, "-c", script]) == 1

    def test_passes_when_nothing_changes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = _init_no_git_scope(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        assert run_guarded([sys.executable, "-c", "import sys; sys.exit(0)"]) == 0
        assert (
            "tree-writes-guard: content snapshot (git refused: fatal: not a git repository"
            in capsys.readouterr().err
        )

    def test_a_clean_command_still_returns_its_own_exit_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_no_git_scope(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        assert run_guarded([sys.executable, "-c", "import sys; sys.exit(3)"]) == 3


_REAL_SUBPROCESS_RUN = subprocess.run

DUBIOUS_OWNERSHIP_STDERR = (
    "fatal: detected dubious ownership in repository at '/repo'\n"
    "To add an exception for this directory, call:\n\n"
    "\tgit config --global --add safe.directory /repo\n"
)


def _fake_run_refusing_git(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Stands in for `subprocess.run`: answers a `git` invocation the way a checkout git refuses
    to read does (rc 128, dubious-ownership stderr -- B-57's exact container failure), and
    otherwise defers to the real `subprocess.run` so the wrapped command under test still
    actually runs."""
    if argv[:1] == ["git"]:
        return subprocess.CompletedProcess(
            argv, returncode=128, stdout="", stderr=DUBIOUS_OWNERSHIP_STDERR
        )
    return _REAL_SUBPROCESS_RUN(argv, **kwargs)


class TestGuardModeSurvivesGitRefusing:
    """B-57: `.git` existing is not proof git can answer for it -- a checkout git refuses to
    read (dubious ownership in a container whose checkout is owned by another uid) must fall
    back to the content-snapshot mode rather than raise the way `working_tree_status` does."""

    def test_guard_mode_falls_back_when_git_refuses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(subprocess, "run", _fake_run_refusing_git)
        mode, reason = tree_writes_guard.guard_mode(repo)
        assert mode == tree_writes_guard.CONTENT_SNAPSHOT_MODE
        assert "dubious ownership" in reason

    def test_printed_mode_line_names_gits_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        monkeypatch.setattr(subprocess, "run", _fake_run_refusing_git)
        run_guarded([sys.executable, "-c", "import sys; sys.exit(0)"])
        err = capsys.readouterr().err
        assert (
            "tree-writes-guard: content snapshot (git refused: "
            "fatal: detected dubious ownership" in err
        )

    def test_a_write_is_still_caught_when_git_refuses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        monkeypatch.setattr(subprocess, "run", _fake_run_refusing_git)
        target = repo / "tracked.md"
        script = (
            f"from pathlib import Path; "
            f"Path({str(target)!r}).write_text('rewritten\\n', encoding='utf-8')"
        )
        assert run_guarded([sys.executable, "-c", script]) == 1


class TestGitModeAnnouncesItsModeOnce:
    def test_prints_the_git_mode_line_exactly_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _init_repo(tmp_path)
        monkeypatch.setattr(tree_writes_guard, "REPO_ROOT", repo)
        run_guarded([sys.executable, "-c", "import sys; sys.exit(0)"])
        assert capsys.readouterr().err.count("tree-writes-guard: git") == 1


class TestBaselineNeverSkipsSilently:
    """Rule: git failing to answer is a failure, not a pass (see the module docstring) -- the
    same holds for the no-`.git` fallback. A baseline it cannot establish at all must fail
    naming why, never read as "nothing to compare, so nothing changed"."""

    def test_a_missing_repo_root_fails_naming_why(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        with pytest.raises(RuntimeError, match="does not exist"):
            tree_writes_guard.content_snapshot(missing)

    def test_an_unreadable_scoped_file_fails_naming_why(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A chmod-000 file does not reproduce this for a root-run CI job -- root reads it anyway
        # -- so the failure is injected instead of relied on from the filesystem, holding the
        # assertion for root and non-root runners alike.
        repo = _init_no_git_scope(tmp_path)
        target = repo / "scripts" / "tracked.py"
        real_read_bytes = Path.read_bytes

        def _fake_read_bytes(self: Path) -> bytes:
            if self == target:
                raise PermissionError(13, "Permission denied", str(target))
            return real_read_bytes(self)

        monkeypatch.setattr(Path, "read_bytes", _fake_read_bytes)
        with pytest.raises(RuntimeError, match=r"tracked\.py"):
            tree_writes_guard.content_snapshot(repo)


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
