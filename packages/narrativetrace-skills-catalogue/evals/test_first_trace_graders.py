# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The two first-trace graders of ``add-narrative-tracing`` (B-92), rehearsed against hand-built
project trees with a stand-in ``uv``: ``happy-path`` (no tests: the grader runs the demo itself and
reads its stdout) and ``existing-service`` (tests: the project's suite passes and left a ``.md``
AND a ``.nt``). Each row asserts the grader's REASON. Resolving and installing real packages is
the trial's job, not this file's."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_CASES = Path(__file__).resolve().parent / "add-narrative-tracing"
_HAPPY = _CASES / "happy-path" / "graders" / "verify.sh"
_EXISTING = _CASES / "existing-service" / "graders" / "verify.sh"

_PYPROJECT = '[project]\nname = "p"\nversion = "0"\ndependencies = ["narrativetrace"]\n'
_TRACE_LINE = 'print(\'OrderService.place_order(customer_id: "c") → "ORD-c" — 0ms #1\')\n'
_DOCTOR = '{"findings": [{"id": "toolchain.python", "status": "pass"}]}'
_FAILING_DOCTOR = '{"findings": [{"id": "toolchain.python", "status": "fail"}]}'

_UV = f"""#!/bin/sh
# stand-in for `uv run ...`: python runs under the test's interpreter, pytest and the doctor answer
# from the environment the test sets.
shift
case "$1" in
  python) shift; exec "{sys.executable}" "$@" ;;
  pytest) exit "${{FAKE_PYTEST_EXIT:-0}}" ;;
  narrativetrace) printf '%s' "$FAKE_DOCTOR_REPORT" ; exit 1 ;;
esac
exit 99
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return root


def _grade(
    grader: Path, project: Path, tmp_path: Path, **env: str
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    uv = bin_dir / "uv"
    uv.write_text(_UV, encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DOCTOR_REPORT": _DOCTOR,
        **env,
    }
    return subprocess.run(  # nosec B603, B607 # fixed argv, test-owned tree
        ["sh", str(grader)],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class TestHappyPathRunsTheDemoItself:
    def test_a_demo_that_prints_a_traced_call_line_passes(
        self, project: Path, tmp_path: Path
    ) -> None:
        (project / "main.py").write_text(_TRACE_LINE, encoding="utf-8")
        result = _grade(_HAPPY, project, tmp_path)
        assert (result.returncode, result.stderr) == (0, "")

    def test_a_demo_under_another_name_is_found_by_its_trace_capture(
        self, project: Path, tmp_path: Path
    ) -> None:
        (project / "demo.py").write_text("# ctx.capture_trace()\n" + _TRACE_LINE, encoding="utf-8")
        assert _grade(_HAPPY, project, tmp_path).returncode == 0

    def test_no_demo_left_behind_fails_naming_the_expectation(
        self, project: Path, tmp_path: Path
    ) -> None:
        result = _grade(_HAPPY, project, tmp_path)
        assert result.returncode != 0
        assert "no demo script left behind" in result.stderr

    def test_a_demo_that_exits_non_zero_fails_with_its_output(
        self, project: Path, tmp_path: Path
    ) -> None:
        (project / "main.py").write_text(
            "import sys\nprint('boom')\nsys.exit(3)\n", encoding="utf-8"
        )
        result = _grade(_HAPPY, project, tmp_path)
        assert result.returncode != 0
        assert "main.py` failed" in result.stderr
        assert "boom" in result.stderr

    def test_a_demo_that_prints_no_traced_call_line_fails(
        self, project: Path, tmp_path: Path
    ) -> None:
        (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
        result = _grade(_HAPPY, project, tmp_path)
        assert result.returncode != 0
        assert "traced call line" in result.stderr

    def test_a_failing_toolchain_finding_still_fails(self, project: Path, tmp_path: Path) -> None:
        (project / "main.py").write_text(_TRACE_LINE, encoding="utf-8")
        result = _grade(_HAPPY, project, tmp_path, FAKE_DOCTOR_REPORT=_FAILING_DOCTOR)
        assert result.returncode != 0
        assert "toolchain.* finding" in result.stderr


@pytest.fixture
def tested_project(project: Path) -> Path:
    (project / "tests").mkdir()
    (project / "tests" / "test_invoice_service.py").write_text("", encoding="utf-8")
    out = project / "narrative-traces"
    out.mkdir()
    (out / "test_x.md").write_text("# trace", encoding="utf-8")
    (out / "test_x.nt").write_text("OrderService.place_order", encoding="utf-8")
    return project


class TestExistingServiceAsksForTheFiles:
    def test_passing_tests_with_md_and_nt_files_pass(
        self, tested_project: Path, tmp_path: Path
    ) -> None:
        result = _grade(_EXISTING, tested_project, tmp_path)
        assert (result.returncode, result.stderr) == (0, "")

    @pytest.mark.parametrize("missing", ["md", "nt"])
    def test_a_missing_artifact_kind_fails_naming_it(
        self, tested_project: Path, tmp_path: Path, missing: str
    ) -> None:
        (tested_project / "narrative-traces" / f"test_x.{missing}").unlink()
        result = _grade(_EXISTING, tested_project, tmp_path)
        assert result.returncode != 0
        assert f"at least one .{missing} file under narrative-traces/" in result.stderr

    def test_no_output_directory_fails(self, tested_project: Path, tmp_path: Path) -> None:
        for artifact in (tested_project / "narrative-traces").iterdir():
            artifact.unlink()
        (tested_project / "narrative-traces").rmdir()
        assert _grade(_EXISTING, tested_project, tmp_path).returncode != 0

    def test_a_failing_suite_fails_before_the_files_are_looked_at(
        self, tested_project: Path, tmp_path: Path
    ) -> None:
        result = _grade(_EXISTING, tested_project, tmp_path, FAKE_PYTEST_EXIT="1")
        assert result.returncode != 0
        assert "the project's own tests must pass" in result.stderr

    def test_a_deleted_fixture_test_fails(self, tested_project: Path, tmp_path: Path) -> None:
        (tested_project / "tests" / "test_invoice_service.py").unlink()
        result = _grade(_EXISTING, tested_project, tmp_path)
        assert result.returncode != 0
        assert "the fixture's own test must still be there" in result.stderr

    def test_a_failing_toolchain_finding_fails(self, tested_project: Path, tmp_path: Path) -> None:
        result = _grade(_EXISTING, tested_project, tmp_path, FAKE_DOCTOR_REPORT=_FAILING_DOCTOR)
        assert result.returncode != 0
        assert "toolchain.* finding" in result.stderr
