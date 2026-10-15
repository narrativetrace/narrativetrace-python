# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ``narrativetrace-explain`` grader, rehearsed BEFORE any trial is spent: on a solved trial, an
untouched project and every near miss the three cases exist to catch. Each row asserts the grader's
REASON — the line it prints — not merely its verdict.

Every project state is real: the fixture's own code, run through the real pytest plugin
(``trace_skill_rehearsal``), so the transcripts carry the trace lines that state actually renders.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "narrativetrace-explain"))
sys.path.insert(0, str(_HERE / "narrativetrace-verify"))

import grade_the_explain as ge  # noqa: E402
import grade_the_verify as gv  # noqa: E402
from trace_skill_rehearsal import Stream, run_pytest, scaffold  # noqa: E402

_FIXTURE = "existing-service-checkout"
_NT = "narrative-traces/structural/test_checkout_flow/test_customer_checks_out.nt"
_MD = "narrative-traces/traces/test_checkout_flow/test_customer_checks_out.md"
_ANSWER = (
    "The checkout is #1 CheckoutService.checkout: it calls InvoiceService.issue_invoice (#1.1), "
    "PaymentGateway.authorize (#1.2), then LedgerService.record_paid (#1.3) and "
    "PaymentGateway.confirm (#1.4). NotificationService was not observed — no span."
)
_CONTROL_ANSWER = (
    "fee_for is a pure function, so I am reading the source: 150 cents a day late, and 0 when it "
    "is on time."
)
_printed: list[str] = []


@pytest.fixture(autouse=True)
def _capture_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    _printed.clear()
    monkeypatch.setattr("builtins.print", _printed.append)


def _traced(tmp_path: Path) -> Path:
    project = scaffold(_FIXTURE, tmp_path)
    assert run_pytest(project, "tests/test_checkout_flow.py")[0]
    return project


def _explain_stream(project: Path, answer: str = _ANSWER, *, invoke: bool = True) -> Stream:
    stream = Stream().user(1, "Show me what this application actually does.")
    if invoke:
        stream.tool("Skill", {"skill": SKILL})
    stream.bash("uv run pytest tests/test_checkout_flow.py", "1 passed")
    nt = (project / _NT).read_text(encoding="utf-8")
    stream.tool("Read", {"file_path": "/s/" + _NT}, nt)
    return stream.say(answer)


SKILL = "narrativetrace-explain"


def _grade(project: Path, stream: Stream, monkeypatch: pytest.MonkeyPatch, kind: str) -> list[str]:
    transcript = stream.write_to(project.parent / "transcript.jsonl")
    monkeypatch.chdir(project)
    verdict = gv.Verdict()
    events = gv.read_events(str(transcript))
    (ge.grade_explain if kind == "explain" else ge.grade_control)(events, verdict)
    return [line for line in _printed]


def _failures(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("FAIL")]


class TestExplainCase:
    def test_a_solved_trial_passes_every_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _traced(tmp_path)

        lines = _grade(project, _explain_stream(project), monkeypatch, "explain")

        assert _failures(lines) == []
        assert "note the flow's calls are named in the order they ran: True" in lines
        assert "note the answer names what was not observed: True" in lines
        assert "note values were opened: False" in lines

    def test_an_answer_written_without_invoking_the_skill_fails_on_that(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _traced(tmp_path)

        lines = _grade(project, _explain_stream(project, invoke=False), monkeypatch, "explain")

        assert _failures(lines) == [
            "FAIL the Skill tool invoked narrativetrace-explain — it never did"
        ]

    def test_an_untouched_project_has_no_trace_and_no_cited_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        stream = Stream().user(1, "Show me what this application does.")
        stream.tool("Skill", {"skill": SKILL}).say(_ANSWER)

        lines = _grade(project, stream, monkeypatch, "explain")

        reasons = _failures(lines)
        assert any("the run left a structural trace in the project" in r for r in reasons)
        assert any("a structural trace reached the agent before its answer" in r for r in reasons)
        assert any("the answer cites a span id the trace it produced" in r for r in reasons)

    def test_a_trace_nobody_read_fails_even_when_the_answer_cites_a_real_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _traced(tmp_path)
        stream = Stream().user(1, "Show me what this application does.")
        stream.tool("Skill", {"skill": SKILL}).bash("uv run pytest", "1 passed").say(_ANSWER)

        reasons = _failures(_grade(project, stream, monkeypatch, "explain"))

        assert len(reasons) == 1
        assert reasons[0].startswith("FAIL a structural trace reached the agent before its answer")
        assert "no structural trace line ever reached the agent" in reasons[0]

    def test_an_id_that_is_in_no_trace_is_not_a_citation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _traced(tmp_path)
        stream = _explain_stream(project, "The checkout is #9.9 and then #8.8, nothing else.")

        reasons = _failures(_grade(project, stream, monkeypatch, "explain"))

        assert len(reasons) == 1
        assert "ids cited ['#8.8', '#9.9'], ids in the trace" in reasons[0]

    def test_explaining_by_rewriting_the_service_fails_the_production_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _traced(tmp_path)
        compose = project / "src" / "billing" / "compose.py"
        compose.write_text(compose.read_text(encoding="utf-8") + "\n# wrapped\n", encoding="utf-8")

        reasons = _failures(_grade(project, _explain_stream(project), monkeypatch, "explain"))

        assert len(reasons) == 1
        assert "the production code and the build were left alone — changed:" in reasons[0]
        assert "src/billing/compose.py" in reasons[0]

    def test_an_added_dependency_fails_the_build_gate_but_a_lockfile_does_not(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _traced(tmp_path)
        (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        assert _failures(_grade(project, _explain_stream(project), monkeypatch, "explain")) == []

        _printed.clear()
        pyproject = project / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8").replace(
                'dependencies = ["narrativetrace"', 'dependencies = ["rich", "narrativetrace"'
            ),
            encoding="utf-8",
        )
        reasons = _failures(_grade(project, _explain_stream(project), monkeypatch, "explain"))

        assert len(reasons) == 1
        assert "changed: [] ['pyproject.toml']" in reasons[0]

    def test_bytecode_the_run_leaves_in_the_source_tree_is_not_a_change(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _traced(tmp_path)
        cache = project / "src" / "billing" / "__pycache__"
        cache.mkdir(exist_ok=True)
        (cache / "compose.cpython-312.pyc").write_bytes(b"\x00")

        assert _failures(_grade(project, _explain_stream(project), monkeypatch, "explain")) == []


class TestControlCase:
    def _control(self, answer: str) -> Stream:
        stream = Stream().user(1, "Explain what fee_for does.")
        stream.tool("Skill", {"skill": SKILL})
        stream.tool("Read", {"file_path": "/s/src/billing/late_fees.py"}, "def fee_for(d): ...")
        return stream.say(answer)

    def test_an_answer_from_the_source_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)

        lines = _grade(project, self._control(_CONTROL_ANSWER), monkeypatch, "control")

        assert _failures(lines) == []
        assert "note the skill was invoked: True" in lines
        assert "note the reply says why it is not tracing: True" in lines

    def test_running_the_suite_to_be_sure_fails_on_nothing_was_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        stream = self._control("unused").bash("uv run pytest -q", "5 passed")
        stream.say(_CONTROL_ANSWER)

        reasons = _failures(_grade(project, stream, monkeypatch, "control"))

        assert len(reasons) == 1
        assert reasons[0].startswith("FAIL nothing was run — the project's tooling ran at event")

    def test_a_word_pytest_in_a_search_is_not_a_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        stream = self._control("unused").bash("grep -rn pytest . | head", "")
        stream.say(_CONTROL_ANSWER)

        assert _failures(_grade(project, stream, monkeypatch, "control")) == []

    def test_a_traced_pure_function_fails_on_nothing_was_traced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _traced(tmp_path)
        stream = self._control("unused").tool(
            "Read", {"file_path": "/s/" + _NT}, (project / _NT).read_text(encoding="utf-8")
        )
        stream.say(_CONTROL_ANSWER)

        reasons = _failures(_grade(project, stream, monkeypatch, "control"))

        assert len(reasons) == 1
        assert reasons[0].startswith("FAIL nothing was traced — traces on disk")

    def test_an_answer_without_the_numbers_fails_on_the_source_reading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)

        reasons = _failures(
            _grade(project, self._control("fee_for prices a late invoice."), monkeypatch, "control")
        )

        assert len(reasons) == 1
        assert reasons[0].startswith(
            "FAIL the answer comes from the source: the function, the rate and the not-late case"
        )

    def test_installing_a_dependency_fails_the_build_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        pyproject = project / "pyproject.toml"
        pyproject.write_text(pyproject.read_text(encoding="utf-8") + "\n# x\n", encoding="utf-8")

        reasons = _failures(_grade(project, self._control(_CONTROL_ANSWER), monkeypatch, "control"))

        assert reasons == [
            "FAIL no dependency was added and no build file changed — changed: ['pyproject.toml']"
        ]

    def test_editing_the_function_fails_the_sources_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        late_fees = project / "src" / "billing" / "late_fees.py"
        late_fees.write_text(late_fees.read_text(encoding="utf-8") + "# note\n", encoding="utf-8")

        reasons = _failures(_grade(project, self._control(_CONTROL_ANSWER), monkeypatch, "control"))

        assert len(reasons) == 1
        assert "src/billing/late_fees.py" in reasons[0]
