# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ``add-narrativetrace-clarity`` grader, rehearsed BEFORE any trial is spent: on a solved
project and on every near miss the case exists to catch. Each row asserts the grader's REASON, not
merely its verdict -- a grader that fails a near miss for the wrong reason passes the next one for
the wrong reason too.

The solved project is the case's own fixture with its names changed, so what is rehearsed is the
fixture the trial will really start from. ``uv`` is replaced by a recorded stand-in: the gate and
the tests are rehearsed for real in ``tests/test_clarity_eval_fixture.py``, and this file is about
what the GRADER does with their results.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_CASE = Path(__file__).resolve().parent / "add-narrativetrace-clarity"
sys.path.insert(0, str(_CASE))

import grade_the_clarity_gate as grader  # noqa: E402

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "clarity-unclear-name"

_RENAMES = (
    ("proc(self, d, x)", "place_order(self, customer_id, quantity)"),
    ('f"ORD-{d}-{x}"', 'f"ORD-{customer_id}-{quantity}"'),
    ("calc(self, val, tmp)", "total_price(self, unit_price, quantity)"),
    ("val * tmp", "unit_price * quantity"),
    ("fmt(self, o)", "format_invoice(self, order_id)"),
    ('f"Invoice for {o}"', 'f"Invoice for {order_id}"'),
)


@dataclass
class FakeUv:
    """Stands in for ``uv run ...``: answers each command the grader asks for, records it."""

    gate_exit: int = 0
    scored: int = 2
    tests_exit: int = 0
    collected: int = 4
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, argv: Sequence[str], cwd: Path) -> grader.Outcome:
        self.calls.append(list(argv))
        if "narrativetrace-clarity" in argv:
            out = Path(argv[argv.index("--output-dir") + 1])
            out.mkdir(parents=True, exist_ok=True)
            scenarios = [{"name": f"C{i}", "issues": []} for i in range(self.scored)]
            (out / "clarity-results.json").write_text(json.dumps({"scenarios": scenarios}))
            return grader.Outcome(self.gate_exit, "")
        if "--collect-only" in argv:
            return grader.Outcome(
                0, "".join(f"tests/t.py::test_{i}\n" for i in range(self.collected))
            )
        return grader.Outcome(self.tests_exit, "")


def _project(tmp_path: Path, *, solved: bool = True, dependency: bool = True) -> Path:
    project = tmp_path / "project"
    shutil.copytree(_FIXTURE, project, ignore=shutil.ignore_patterns("__pycache__"))
    if solved:
        source = project / "src" / "orders" / "order_service.py"
        text = source.read_text(encoding="utf-8")
        for old, new in _RENAMES:
            text = text.replace(old, new)
        source.write_text(text, encoding="utf-8")
    if dependency:
        pyproject = project / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8").replace(
                'dev = ["pytest>=8"]', 'dev = ["pytest>=8", "narrativetrace-clarity"]'
            ),
            encoding="utf-8",
        )
    return project


def _reasons(project: Path, uv: FakeUv) -> list[str]:
    return grader.grade(project, uv)


class TestASolvedProject:
    def test_passes_with_nothing_to_say(self, tmp_path: Path) -> None:
        assert _reasons(_project(tmp_path), FakeUv()) == []

    def test_runs_the_gate_over_src_with_the_thresholds_the_prompt_names(
        self, tmp_path: Path
    ) -> None:
        uv = FakeUv()
        _reasons(_project(tmp_path), uv)

        gate = next(call for call in uv.calls if "narrativetrace-clarity" in call)
        assert gate[:4] == ["uv", "run", "narrativetrace-clarity", "src"]
        assert gate[gate.index("--min-score") + 1] == "0.6"
        assert gate[gate.index("--max-high-issues") + 1] == "0"

    def test_writes_the_gates_reports_outside_the_project(self, tmp_path: Path) -> None:
        uv = FakeUv()
        project = _project(tmp_path)
        _reasons(project, uv)

        gate = next(call for call in uv.calls if "narrativetrace-clarity" in call)
        assert project not in Path(gate[gate.index("--output-dir") + 1]).parents
        assert not (project / "build").exists()


class TestNearMisses:
    def test_the_untouched_project_fails_because_the_gate_does(self, tmp_path: Path) -> None:
        reasons = _reasons(_project(tmp_path, solved=False), FakeUv(gate_exit=1))

        assert reasons == ["the gate exits 1 on `src` with --min-score 0.6 --max-high-issues 0"]

    def test_a_project_that_never_added_the_gate_fails_for_that_alone(self, tmp_path: Path) -> None:
        reasons = _reasons(_project(tmp_path, dependency=False), FakeUv())

        assert reasons == ["pyproject.toml does not declare narrativetrace-clarity"]

    def test_the_dependency_may_sit_in_the_runtime_dependencies_too(self, tmp_path: Path) -> None:
        project = _project(tmp_path, dependency=False)
        pyproject = project / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8").replace(
                "dependencies = []", 'dependencies = ["narrativetrace-clarity>=0.2"]'
            ),
            encoding="utf-8",
        )

        assert _reasons(project, FakeUv()) == []

    def test_a_gate_that_scored_one_class_is_not_a_clean_gate(self, tmp_path: Path) -> None:
        reasons = _reasons(_project(tmp_path), FakeUv(scored=1))

        assert reasons == ["the gate scored 1 class(es); the project has 2 public ones"]

    def test_a_gate_that_scored_nothing_is_not_a_clean_gate(self, tmp_path: Path) -> None:
        reasons = _reasons(_project(tmp_path), FakeUv(scored=0))

        assert reasons == ["the gate scored 0 class(es); the project has 2 public ones"]

    def test_deleting_a_method_to_satisfy_the_gate_fails(self, tmp_path: Path) -> None:
        project = _project(tmp_path)
        source = project / "src" / "orders" / "order_service.py"
        text = source.read_text(encoding="utf-8")
        source.write_text(
            text[: text.index("    def total_price")] + text[text.index("class Invoice") :]
        )

        reasons = _reasons(project, FakeUv())

        assert reasons == ["the project has 2 public methods; it started with 3"]

    def test_failing_tests_fail_the_case(self, tmp_path: Path) -> None:
        reasons = _reasons(_project(tmp_path), FakeUv(tests_exit=1))

        assert reasons == ["the project's tests fail after the renames"]

    def test_deleting_a_test_to_make_the_suite_pass_fails(self, tmp_path: Path) -> None:
        reasons = _reasons(_project(tmp_path), FakeUv(collected=3))

        assert reasons == ["3 tests remain; the project started with 4"]

    def test_warn_only_in_any_project_file_fails(self, tmp_path: Path) -> None:
        project = _project(tmp_path)
        (project / "ci.yml").write_text("run: narrativetrace-clarity src --warn-only\n")

        reasons = _reasons(project, FakeUv())

        assert reasons == ["ci.yml turns the gate advisory with --warn-only"]

    def test_warn_only_inside_the_virtual_environment_is_not_the_projects(
        self, tmp_path: Path
    ) -> None:
        project = _project(tmp_path)
        (project / ".venv" / "lib").mkdir(parents=True)
        (project / ".venv" / "lib" / "cli.py").write_text("--warn-only\n")

        assert _reasons(project, FakeUv()) == []

    @pytest.mark.parametrize("pages", [".claude", ".agents"])
    def test_warn_only_in_the_skill_pages_the_harness_copied_in_is_not_the_projects(
        self, tmp_path: Path, pages: str
    ) -> None:
        """The clarity skill's own page says never to add the flag. A trial that really passed
        failed on exactly this line (2026-10-09), so the pages are the harness's, not the
        project's."""
        project = _project(tmp_path)
        page = project / pages / "skills" / "add-narrativetrace-clarity" / "SKILL.md"
        page.parent.mkdir(parents=True)
        page.write_text("- Never add --warn-only to make the gate go green.\n")

        assert _reasons(project, FakeUv()) == []

    def test_every_failure_is_reported_not_only_the_first(self, tmp_path: Path) -> None:
        reasons = _reasons(_project(tmp_path, dependency=False), FakeUv(gate_exit=1, tests_exit=1))

        assert reasons == [
            "pyproject.toml does not declare narrativetrace-clarity",
            "the gate exits 1 on `src` with --min-score 0.6 --max-high-issues 0",
            "the project's tests fail after the renames",
        ]


class TestMain:
    @pytest.mark.parametrize(("reasons", "code"), [([], 0), (["a reason"], 1)])
    def test_exits_by_the_verdict_and_says_why(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        reasons: list[str],
        code: int,
    ) -> None:
        monkeypatch.setattr(grader, "grade", lambda *_: reasons)

        assert grader.main() == code
        assert capsys.readouterr().err.splitlines() == reasons
