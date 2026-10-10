# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial unit tests for the ``add-narrativetrace-clarity`` eval plumbing: the fresh-report
snippet, the grader's dependency, shape, advisory-flag and count rules, and the git helpers in
``run.py``. Written by a cheap model against the code, then read: each test asserts what a careful
engineer would want, and the defects it found (a signing git configuration, a dotted package
name, an unparseable source, a nested ``build`` directory, a missing project file) are fixed
rather than recorded."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from narrativetrace_skills.catalogue.clarity_commands import REPORTS_FRESH_CODE

_EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(_EVALS))
sys.path.insert(0, str(_EVALS / "add-narrativetrace-clarity"))

import grade_the_clarity_gate as grader  # noqa: E402
import run  # noqa: E402

_ONE_CLASS = json.dumps({"scenarios": [{"name": "A", "issues": []}]}).encode()
_PASS = grader.Outcome(0, "")
_NO_DEP = "pyproject.toml does not declare narrativetrace-clarity"


def _refused(cwd: Path) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, "-I", "-c", REPORTS_FRESH_CODE]
    return subprocess.run(  # nosec B603 - this interpreter, the catalogue's own snippet
        argv, cwd=cwd, capture_output=True, text=True, check=False
    )


def _pair(cwd: Path, results: bytes = _ONE_CLASS) -> Path:
    out = cwd / "build" / "narrativetrace"
    out.mkdir(parents=True)
    (out / "clarity-results.json").write_bytes(results)
    (out / "clarity-report.md").write_text("# r\n", encoding="utf-8")
    return out


def _age(path: Path, seconds: float) -> None:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


class TestFreshReportBoundary:
    def test_a_pair_aged_599_seconds_is_still_fresh(self, tmp_path: Path) -> None:
        for artefact in _pair(tmp_path).iterdir():
            _age(artefact, 599)
        assert _refused(tmp_path).returncode == 0

    def test_a_pair_aged_601_seconds_is_stale(self, tmp_path: Path) -> None:
        for artefact in _pair(tmp_path).iterdir():
            _age(artefact, 601)
        result = _refused(tmp_path)
        assert result.returncode == 1
        assert "stale" in result.stderr

    def test_one_stale_file_makes_the_pair_stale(self, tmp_path: Path) -> None:
        _age(_pair(tmp_path) / "clarity-report.md", 3600)
        result = _refused(tmp_path)
        assert result.returncode == 1
        assert "stale" in result.stderr


class TestResultsFileShape:
    def test_a_results_file_that_is_not_utf8_is_refused_as_not_a_report(
        self, tmp_path: Path
    ) -> None:
        _pair(tmp_path, results=b'{"scenarios": [{"name": "\xff"}]}')
        result = _refused(tmp_path)
        assert result.returncode == 1
        assert "not a clarity report" in result.stderr

    @pytest.mark.parametrize("body", [b"[1, 2]", b'"scenarios"', b""])
    def test_a_results_file_that_is_not_an_object_is_refused(
        self, tmp_path: Path, body: bytes
    ) -> None:
        _pair(tmp_path, results=body)
        assert _refused(tmp_path).returncode == 1


class TestGitRepositoryDeclaration:
    def test_git_is_a_repository_and_no_manifest_or_no_key_is_not(self, tmp_path: Path) -> None:
        assert run._declares_a_git_repository(tmp_path) is False
        (tmp_path / "case.json").write_text('{"install": "checkout"}')
        assert run._declares_a_git_repository(tmp_path) is False
        (tmp_path / "case.json").write_text('{"vcs": "git"}')
        assert run._declares_a_git_repository(tmp_path) is True

    @pytest.mark.parametrize("declared", ['"svn"', '"Git"', '"git "', "null", '""'])
    def test_any_other_vcs_value_is_refused(self, tmp_path: Path, declared: str) -> None:
        (tmp_path / "case.json").write_text('{"vcs": ' + declared + "}")
        with pytest.raises(ValueError, match="the only vcs a case may declare"):
            run._declares_a_git_repository(tmp_path)


def _failing(verb: str, error: Exception):  # type: ignore[no-untyped-def]
    def spawn(argv, cwd, env, **_):  # type: ignore[no-untyped-def]
        if verb in argv:
            raise error

    return spawn


class TestCommitTheProject:
    def test_a_failing_commit_is_a_crash_with_no_ledger_row(self, tmp_path: Path) -> None:
        spawn = _failing("commit", subprocess.CalledProcessError(1, "git"))
        with pytest.raises(RuntimeError, match="no project to work in"):
            run._commit_the_project(tmp_path, spawn)

    def test_the_fixture_commit_ignores_the_developers_global_git_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        global_config = tmp_path / "gitconfig"
        global_config.write_text("[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = /nonexistent\n")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
        scratch = tmp_path / "project"
        scratch.mkdir()
        (scratch / "a.py").write_text("x = 1\n")
        run._commit_the_project(scratch, run.default_spawner)


def _missing(tmp_path: Path, pyproject: str) -> list[str]:
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return grader._dependency_missing(tmp_path)


class TestDependencyNames:
    def test_a_pinned_extra_with_a_python_marker_is_declared(self, tmp_path: Path) -> None:
        marked = 'Narrativetrace_Clarity[x]>=0.2 ; python_version>"3.8"'
        assert _missing(tmp_path, f"[project]\ndependencies = ['{marked}']\n") == []

    def test_the_name_is_matched_case_insensitively(self, tmp_path: Path) -> None:
        assert _missing(tmp_path, '[project]\ndependencies = ["NARRATIVETRACE-CLARITY"]\n') == []

    def test_an_include_group_entry_does_not_hide_the_named_group(self, tmp_path: Path) -> None:
        text = (
            '[dependency-groups]\nall = [{include-group = "dev"}]\n'
            'dev = ["narrativetrace-clarity"]\n'
        )
        assert _missing(tmp_path, text) == []

    def test_an_include_group_entry_alone_declares_nothing(self, tmp_path: Path) -> None:
        text = '[dependency-groups]\nall = [{include-group = "dev"}]\n'
        assert _missing(tmp_path, text) == [_NO_DEP]

    def test_a_dotted_spelling_of_the_name_is_declared(self, tmp_path: Path) -> None:
        assert _missing(tmp_path, '[project]\ndependencies = ["narrativetrace.clarity"]\n') == []


class TestTheProjectFile:
    def test_a_missing_project_file_is_a_reason_not_a_crash(self, tmp_path: Path) -> None:
        assert grader._dependency_missing(tmp_path) == ["pyproject.toml is missing"]

    def test_a_project_file_that_is_not_toml_is_a_reason_not_a_crash(self, tmp_path: Path) -> None:
        assert _missing(tmp_path, "[project\n") == ["pyproject.toml is not valid TOML"]


def _src(tmp_path: Path, source: str) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text(source, encoding="utf-8")
    return tmp_path


class TestPublicShape:
    def test_async_methods_count_as_public_methods(self, tmp_path: Path) -> None:
        source = "class A:\n    async def run(self): ...\n"
        assert grader._public_shape(_src(tmp_path, source)) == (1, 1)

    def test_private_classes_and_private_methods_are_not_counted(self, tmp_path: Path) -> None:
        source = "class _Hidden:\n    def a(self): ...\nclass Public:\n    def _x(self): ...\n"
        assert grader._public_shape(_src(tmp_path, source)) == (1, 0)

    def test_a_project_without_src_fails_with_reasons_not_a_crash(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["narrativetrace-clarity"]\n'
        )
        reasons = grader.grade(tmp_path, lambda argv, cwd: grader.Outcome(2, ""))
        assert any("public methods" in reason for reason in reasons)

    def test_a_syntax_error_under_src_is_a_reason_naming_the_file(self, tmp_path: Path) -> None:
        reasons = grader.grade(_src(tmp_path, "def broken(:\n"), lambda argv, cwd: _PASS)
        assert any("m.py" in reason for reason in reasons)


class TestAdvisoryFlag:
    def test_warn_only_inside_a_binary_file_is_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "gate.bin").write_bytes(b"\x00\xff\x10--warn-only\x00")
        assert grader._advisory_gates(tmp_path) == [
            "gate.bin turns the gate advisory with --warn-only"
        ]

    def test_warn_only_in_a_nested_build_directory_is_flagged(self, tmp_path: Path) -> None:
        (tmp_path / "ci" / "build").mkdir(parents=True)
        (tmp_path / "ci" / "build" / "check.sh").write_text("narrativetrace-clarity --warn-only\n")
        assert grader._advisory_gates(tmp_path) != []


class TestScoredCount:
    @pytest.mark.parametrize("body", ["{", "[1]", '{"scenarios": null}', '{"other": []}'])
    def test_malformed_results_score_nothing(self, tmp_path: Path, body: str) -> None:
        (tmp_path / "clarity-results.json").write_text(body, encoding="utf-8")
        assert grader._scored(tmp_path) == 0

    def test_scenarios_that_are_an_object_score_nothing(self, tmp_path: Path) -> None:
        (tmp_path / "clarity-results.json").write_text('{"scenarios": {"a": {}, "b": {}}}')
        assert grader._scored(tmp_path) == 0
