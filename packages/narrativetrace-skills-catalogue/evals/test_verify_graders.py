# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ``narrativetrace-verify`` grader, rehearsed BEFORE any trial is spent: on a solved trial, an
untouched project and every near miss the cases exist to catch. Each row asserts the grader's
REASON — the line it prints — not merely its verdict.

Every project state is real: the fixture's own code with the change applied, run through the real
pytest plugin, pinned by the real approve verb (``trace_skill_rehearsal``). Transcripts carry the
trace lines that state actually renders.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "narrativetrace-verify"))

import grade_the_verify as gv
from trace_skill_rehearsal import (
    Stream,
    patched_test_runner,
    pin,
    run_pytest,
    scaffold,
)

_FIXTURE = "existing-service-checkout"
_FLOW = "narrative-traces/structural/test_checkout_flow/test_customer_checks_out.nt"
_INTENT = (
    "Intent: CheckoutService.checkout issues the invoice, PaymentGateway.authorize then "
    "PaymentGateway.confirm, and only then NotificationService.send, once."
)
_RECEIPT_ON = """
    @hooks.on("{hook}")
    def send_receipt(invoice):
        notifications.send(invoice.customer_id, f"Receipt for {{invoice.invoice_id}}")

    return CheckoutService"""


def _add_receipt(project: Path, hook: str) -> None:
    compose = project / "src" / "billing" / "compose.py"
    text = compose.read_text(encoding="utf-8")
    compose.write_text(
        text.replace("\n    return CheckoutService", _RECEIPT_ON.format(hook=hook)),
        encoding="utf-8",
    )


def _grade(project: Path, stream: Stream, monkeypatch: pytest.MonkeyPatch, kind: str) -> list[str]:
    transcript = stream.write_to(project.parent / "transcript.jsonl")
    monkeypatch.chdir(project)
    verdict = gv.Verdict()
    events = gv.read_events(str(transcript))
    with patched_test_runner(gv, project):
        if kind == "skip":
            gv.grade_skip(events, verdict)
        else:
            gv.grade_interaction(
                events, verdict, "NotificationService.send", "PaymentGateway.confirm"
            )
    return [line for line in _printed]


_printed: list[str] = []


@pytest.fixture(autouse=True)
def _capture_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    _printed.clear()
    monkeypatch.setattr("builtins.print", _printed.append)


def _nt(project: Path) -> str:
    return (project / _FLOW).read_text(encoding="utf-8")


def _solved(tmp_path: Path) -> tuple[Path, str, str]:
    """The trap first (a payment_succeeded hook), read, then fixed on checkout_completed and
    pinned: returns the project and the two .nt texts the agent saw."""
    project = scaffold(_FIXTURE, tmp_path)
    _add_receipt(project, "payment_succeeded")
    run_pytest(project)
    wrong = _nt(project)
    compose = project / "src" / "billing" / "compose.py"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace(
            '"payment_succeeded")\n    def send_receipt',
            '"checkout_completed")\n    def send_receipt',
        ),
        encoding="utf-8",
    )
    run_pytest(project)
    fixed = _nt(project)
    pin(project)
    return project, wrong, fixed


def _loop(wrong: str, fixed: str, *, intent_first: bool = True) -> Stream:
    stream = Stream().user(1, "Customers should get a receipt ...")
    stream.tool("Skill", {"skill": "narrativetrace-verify"})
    stream.context("## 2. Write the intent down before running anything — under the word Intent")
    if intent_first:
        stream.say(_INTENT)
    stream.bash("uv run pytest tests/test_checkout_flow.py", "1 passed")
    if not intent_first:
        stream.say(_INTENT)
    stream.tool("Read", {"file_path": "/s/" + _FLOW}, wrong)
    stream.say("Mismatch: #1.4 NotificationService.send runs before #1.5 PaymentGateway.confirm.")
    stream.tool("Edit", {"file_path": "/s/src/billing/compose.py"})
    stream.bash("uv run pytest tests/test_checkout_flow.py", "1 passed")
    stream.tool("Read", {"file_path": "/s/" + _FLOW}, fixed)
    stream.say("Now #1.4 PaymentGateway.confirm comes before #1.5 NotificationService.send.")
    stream.bash("uv run pytest || true", "1 failed, 4 passed")
    stream.say(
        fixed + "\nThe trace showed #1.5 NotificationService.send after #1.4. Shall I pin it?"
    )
    return stream


def _yes(stream: Stream) -> Stream:
    stream.user(2, "yes, pin it")
    stream.bash("uv run narrativetrace-approve", "Approved: test-narratives/...")
    return stream.say(
        "Pinned: #1.5 NotificationService.send now follows #1.4 PaymentGateway.confirm."
    )


class TestInteractionSolved:
    def test_a_solved_trial_passes_every_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project, wrong, fixed = _solved(tmp_path)

        lines = _grade(project, _yes(_loop(wrong, fixed)), monkeypatch, "interaction")

        assert [line for line in lines if line.startswith("FAIL")] == []
        assert (
            "PASS in the final run, NotificationService.send follows PaymentGateway.confirm"
            in lines
        )
        assert "PASS the report names what the trace showed by span id" in lines
        assert "note what was promoted was shown whole in a reply before the yes: True" in lines

    def test_the_skill_page_saying_intent_is_not_the_agents_intent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Item 8: only assistant-record text is the agent's own words."""
        project, wrong, fixed = _solved(tmp_path)

        lines = _grade(
            project, _yes(_loop(wrong, fixed, intent_first=False)), monkeypatch, "interaction"
        )

        assert any(
            line.startswith("FAIL the intent is written before the first traced run")
            for line in lines
        )


class TestInteractionNearMisses:
    def test_the_untouched_project_fails_on_the_flow_and_the_pin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        stream = Stream().user(1, "Customers should ...").say("Done, tests pass.")

        lines = _grade(project, stream, monkeypatch, "interaction")

        failed = {line.split(" — ")[0] for line in lines if line.startswith("FAIL")}
        assert "FAIL the structural trace was read before the report" in failed
        assert (
            "FAIL in the final run, NotificationService.send follows PaymentGateway.confirm"
            in failed
        )
        assert "FAIL a baseline pinning the fixed flow exists" in failed

    def test_read_the_trace_but_did_not_act(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        _add_receipt(project, "payment_succeeded")
        run_pytest(project)
        wrong = _nt(project)
        pin(project)

        lines = _grade(project, _yes(_loop(wrong, wrong)), monkeypatch, "interaction")

        failed = {line.split(" — ")[0] for line in lines if line.startswith("FAIL")}
        assert failed == {
            "FAIL in the final run, NotificationService.send follows PaymentGateway.confirm",
            "FAIL a baseline pinning the fixed flow exists",
            "FAIL the report names what the trace showed by span id",
        }

    def test_values_first(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project, _wrong, fixed = _solved(tmp_path)
        stream = Stream().user(1, "Customers should ...").say(_INTENT)
        stream.bash("uv run pytest", "5 passed")
        stream.tool(
            "Read",
            {"file_path": "/s/narrative-traces/traces/x.md"},
            '- **CheckoutService.checkout**(customer_id: `"C-1001"`) #1',
        )
        stream.tool("Read", {"file_path": "/s/" + _FLOW}, fixed)
        stream.say(fixed + "\nShall I pin #1.5?")

        lines = _grade(project, _yes(stream), monkeypatch, "interaction")

        assert any(
            line.startswith("FAIL values were not opened before the structural trace")
            for line in lines
        )

    def test_pinned_before_the_yes_and_no_question(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project, wrong, fixed = _solved(tmp_path)
        stream = (
            _loop(wrong, fixed).bash("uv run narrativetrace-approve", "Approved").say("Pinned.")
        )

        lines = _grade(project, _yes(stream), monkeypatch, "interaction")

        failed = {line.split(" — ")[0] for line in lines if line.startswith("FAIL")}
        assert "FAIL nothing was promoted before the scripted yes" in failed
        assert "FAIL the turn before the yes ended on the question" in failed

    def test_a_report_without_an_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project, _wrong, fixed = _solved(tmp_path)
        stream = Stream().user(1, "Customers should ...").say(_INTENT)
        stream.bash("uv run pytest", "5 passed")
        stream.tool("Read", {"file_path": "/s/" + _FLOW}, fixed)
        stream.say(fixed + "\nThe receipt goes out after the payment. Pin it?")
        stream.user(2, "yes, pin it").bash("uv run narrativetrace-approve").say("Pinned the flow.")

        lines = _grade(project, stream, monkeypatch, "interaction")

        assert any(
            line.startswith("FAIL the report names what the trace showed by span id")
            for line in lines
        )


def _cap(project: Path) -> None:
    fees = project / "src" / "billing" / "late_fees.py"
    fees.write_text(
        fees.read_text(encoding="utf-8").replace(
            "return days_late * 150", "return min(days_late * 150, 2000)"
        ),
        encoding="utf-8",
    )


class TestSkip:
    def test_a_skipped_pure_function_change_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        _cap(project)
        stream = Stream().user(1, "Late fees should never exceed 2000 cents ...")
        stream.tool("Skill", {"skill": "narrativetrace-verify"})
        stream.bash("uv run pytest tests/test_late_fees.py", "2 passed")
        stream.say("skipping narrativetrace-verify: a pure function with no collaborator.")

        lines = _grade(project, stream, monkeypatch, "skip")

        assert [line for line in lines if line.startswith("FAIL")] == []

    def test_the_untouched_project_fails_on_the_cap_and_the_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)

        lines = _grade(project, Stream().user(1, "Late fees ...").say("Done."), monkeypatch, "skip")

        failed = {line.split(" — ")[0] for line in lines if line.startswith("FAIL")}
        assert failed == {
            "FAIL the late fee is capped at 2000 cents",
            "FAIL the transcript says the skill was skipped and why",
        }

    def test_tracing_the_trivial_change_anyway(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        _cap(project)
        run_pytest(project)
        stream = Stream().user(1, "Late fees ...").say("Intent: fee_for caps at 2000.")
        stream.bash("uv run pytest", "5 passed")
        stream.tool("Read", {"file_path": "/s/" + _FLOW}, _nt(project))
        stream.say("skipping the pin: a pure function.")

        lines = _grade(project, stream, monkeypatch, "skip")

        failed = {line.split(" — ")[0] for line in lines if line.startswith("FAIL")}
        assert failed == {"FAIL no structural trace was read for a pure-function change"}

    def test_switching_approval_on_for_a_pure_function(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        _cap(project)
        pin(project)
        stream = (
            Stream()
            .user(1, "Late fees ...")
            .say("skipping narrativetrace-verify: a pure function.")
        )

        lines = _grade(project, stream, monkeypatch, "skip")

        failed = {line.split(" — ")[0] for line in lines if line.startswith("FAIL")}
        assert failed == {
            "FAIL no approval baseline was written",
            "FAIL approval mode was not switched on",
        }


def _bash_event(command: str) -> gv.Event:
    return gv.Event(1, "tool", {"name": "Bash", "input": {"command": command}})


class TestPureFunctions:
    """Adversarial pass: promotion is judged by what a command does, not the words it names."""

    @pytest.mark.parametrize(
        "command",
        [
            "uv run narrativetrace-approve",
            "narrativetrace-approve --approved-dir test-narratives",
            "uv run poe approve",
            "cp a.received.nt test-narratives/T/a.approved.nt",
            "mv x test-narratives/T/a.approved.nt 2>&1",
            "cat x | tee test-narratives/T/a.approved.nt",
            "cat x > test-narratives/T/a.approved.nt",
            "bash -c 'uv run narrativetrace-approve'",
            "env FOO=1 uv run narrativetrace-approve",
        ],
    )
    def test_a_promotion_in_any_shape_is_one(self, command: str) -> None:
        assert gv.promotes(_bash_event(command))

    @pytest.mark.parametrize(
        "command",
        [
            "grep cp test-narratives/T/a.approved.nt",
            "cat test-narratives/T/a.approved.nt",
            "cp test-narratives/T/a.approved.nt /tmp/x",
            "grep -rn narrativetrace-approve .claude/skills",
            "uv run narrativetrace-approved",
        ],
    )
    def test_a_read_that_names_a_baseline_or_the_verb_is_not(self, command: str) -> None:
        assert not gv.promotes(_bash_event(command))

    def test_a_backup_of_the_skill_page_is_not_the_skill(self) -> None:
        backup = gv.Event(
            1,
            "tool",
            {"name": "Read", "input": {"file_path": "/w/narrativetrace-verify/SKILL.md.bak"}},
        )
        assert not gv.is_skill_load(backup)

    def test_shown_means_the_whole_call_line_parameters_included(self) -> None:
        events = [gv.Event(1, "text", "#1 - Svc.run(other)")]
        assert not gv.shown_before(events, 2, "#1 - Svc.run(amount)\n")
        assert gv.shown_before(
            [gv.Event(1, "text", "  #1 - Svc.run(amount)")], 2, "#1 - Svc.run(amount)\n"
        )
