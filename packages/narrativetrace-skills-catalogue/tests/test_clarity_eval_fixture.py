# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The Tier B fixture of the ``add-narrativetrace-clarity`` case, held to what its README promises:
the gate flags it as it stands, a solved copy passes the case's gate with its tests green, and the
case's numbers agree with the grader's.

A fixture the gate does not flag grades nothing; one the gate cannot be satisfied on grades the
skill for an impossible task. Both are checked here, with the real gate and the real test runner,
before a trial is spent on it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from narrativetrace_clarity.cli import main as clarity_main

_EVALS = Path(__file__).resolve().parents[1] / "evals"
_FIXTURE = _EVALS / "fixtures" / "clarity-unclear-name"
_CASE = _EVALS / "add-narrativetrace-clarity"
sys.path.insert(0, str(_CASE))

import grade_the_clarity_gate as grader  # noqa: E402

_SOLUTION = {
    "src/orders/order_service.py": (
        ("proc(self, d, x)", "place_order(self, customer_id, quantity)"),
        ('f"ORD-{d}-{x}"', 'f"ORD-{customer_id}-{quantity}"'),
        ("calc(self, val, tmp)", "total_price(self, unit_price, quantity)"),
        ("val * tmp", "unit_price * quantity"),
        ("fmt(self, o)", "format_invoice(self, order_id)"),
        ('f"Invoice for {o}"', 'f"Invoice for {order_id}"'),
    ),
    "tests/test_order_service.py": (
        ('proc(d="cust-7", x=3)', 'place_order(customer_id="cust-7", quantity=3)'),
        (".proc(", ".place_order("),
        (".calc(", ".total_price("),
        (".fmt(", ".format_invoice("),
    ),
}


def _copy(tmp_path: Path, *, solved: bool) -> Path:
    project = tmp_path / ("solved" if solved else "as-it-stands")
    shutil.copytree(_FIXTURE, project, ignore=shutil.ignore_patterns("__pycache__"))
    if solved:
        for relative, renames in _SOLUTION.items():
            path = project / relative
            text = path.read_text(encoding="utf-8")
            for old, new in renames:
                assert old in text, (relative, old)
                text = text.replace(old, new)
            path.write_text(text, encoding="utf-8")
    return project


def _the_gate(project: Path, out: Path) -> int:
    return clarity_main(
        [
            str(project / grader.SOURCE),
            "--output-dir",
            str(out),
            "--min-score",
            grader.MIN_SCORE,
            "--max-high-issues",
            grader.MAX_HIGH_ISSUES,
        ]
    )


def _the_projects_tests(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - this interpreter, fixed arguments
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(project),
            "-c",
            str(project / "pyproject.toml"),
            str(project / "tests"),
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )


class TestTheFixtureAsItStands:
    def test_the_gate_flags_it(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        project = _copy(tmp_path, solved=False)

        assert _the_gate(project, tmp_path / "out") == 1

        refusals = capsys.readouterr().err
        assert "OrderService: overall" in refusals
        assert "InvoiceFormatter: overall" in refusals
        assert "7 HIGH-severity issues exceed --max-high-issues 0" in refusals

    def test_the_projects_own_tests_pass(self, tmp_path: Path) -> None:
        done = _the_projects_tests(_copy(tmp_path, solved=False))

        assert done.returncode == 0, done.stdout
        assert "4 passed" in done.stdout

    def test_it_declares_no_clarity_dependency_because_adding_it_is_the_agents_job(self) -> None:
        assert "narrativetrace" not in (_FIXTURE / "pyproject.toml").read_text(encoding="utf-8")


class TestASolvedCopy:
    def test_passes_the_cases_own_gate_having_scored_both_classes(self, tmp_path: Path) -> None:
        project = _copy(tmp_path, solved=True)

        assert _the_gate(project, tmp_path / "out") == 0

        scenarios = json.loads((tmp_path / "out" / "clarity-results.json").read_text())["scenarios"]
        assert sorted(s["name"] for s in scenarios) == ["InvoiceFormatter", "OrderService"]

    def test_keeps_every_test_green_because_the_callers_moved_with_the_names(
        self, tmp_path: Path
    ) -> None:
        done = _the_projects_tests(_copy(tmp_path, solved=True))

        assert done.returncode == 0, done.stdout
        assert "4 passed" in done.stdout

    def test_a_rename_that_leaves_the_keyword_caller_behind_fails_the_suite(
        self, tmp_path: Path
    ) -> None:
        project = _copy(tmp_path, solved=True)
        test = project / "tests" / "test_order_service.py"
        test.write_text(
            test.read_text(encoding="utf-8").replace(
                'place_order(customer_id="cust-7", quantity=3)', 'place_order(d="cust-7", x=3)'
            ),
            encoding="utf-8",
        )

        assert _the_projects_tests(project).returncode == 1


class TestTheCaseAgreesWithTheGrader:
    def test_the_baselines_are_what_the_fixture_has(self) -> None:
        classes, methods = grader._public_shape(_FIXTURE)
        tests = (_FIXTURE / "tests" / "test_order_service.py").read_text(encoding="utf-8")

        assert (classes, methods) == (2, grader.METHODS_AT_START)
        assert tests.count("\ndef test_") == grader.TESTS_AT_START

    def test_the_prompt_asks_for_exactly_the_thresholds_the_grader_runs(self) -> None:
        prompt = (_CASE / "happy-path" / "prompt.md").read_text(encoding="utf-8")

        assert f"at least {grader.MIN_SCORE}" in prompt
        assert "no HIGH issues" in prompt

    def test_the_case_starts_a_committed_project_built_from_this_checkout(self) -> None:
        case = json.loads((_CASE / "happy-path" / "case.json").read_text(encoding="utf-8"))

        assert case == {
            "fixture": (
                "packages/narrativetrace-skills-catalogue/evals/fixtures/clarity-unclear-name"
            ),
            "install": "checkout",
            "vcs": "git",
        }
