# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace-verify`` — Phase 7 D1's loop, D2's cost rule first, D3's flavour table as a
shared reference section, and the pin behind the feedback skill's own gate wording."""

from __future__ import annotations

from pathlib import Path

from narrativetrace_skills.catalogue.approval_gate import (
    end_the_turn_on_the_question,
    never_edit_after_showing,
    never_in_the_turn_that_asked,
    show_the_whole_before_asking,
)
from narrativetrace_skills.catalogue.narrativetrace_feedback import NARRATIVETRACE_FEEDBACK
from narrativetrace_skills.catalogue.narrativetrace_verify import NARRATIVETRACE_VERIFY
from narrativetrace_skills.catalogue.trace_reading import FLAVOURS, SHAPES
from narrativetrace_skills.catalogue.verify_commands import (
    APPROVAL_MODE_IS_ON,
    APPROVE,
    LIST_NARRATIVES,
    LIST_RECEIVED,
    LIST_STRUCTURAL,
    RUN_THE_PATH,
    RUN_THE_SUITE,
    RUN_THE_SUITE_FOR_REVIEW,
)
from narrativetrace_skills.catalogue_index import SKILLS
from narrativetrace_skills.lints import promotion_not_pre_approved
from narrativetrace_skills.skill import CommandStep, SkillStep, SnippetStep

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _step(title: str) -> SkillStep:
    return next(step for step in NARRATIVETRACE_VERIFY.steps if step.title == title)


class TestShape:
    def test_is_in_the_catalogue_once(self) -> None:
        assert [s.canonical_name for s in SKILLS].count("narrativetrace-verify") == 1

    def test_is_a_guided_skill_that_declares_no_allowed_tools(self) -> None:
        assert NARRATIVETRACE_VERIFY.skill_class == "guided"
        assert NARRATIVETRACE_VERIFY.allowed_tools == ()
        assert promotion_not_pre_approved((NARRATIVETRACE_VERIFY,)) == ()

    def test_the_loop_then_the_pin_then_the_report(self) -> None:
        assert [step.title for step in NARRATIVETRACE_VERIFY.steps] == [
            "Decide whether to trace, and say so",
            "Write the intent down before running anything",
            "Run the smallest real path with tracing on",
            "Read the structural trace first, against the intent",
            "Open values on the span that looks wrong, and only there",
            "Fix, re-run, read again",
            "Turn approval mode on",
            "Run the suite in approval mode and show every .received.nt",
            "Ask once whether to pin it, then stop the turn",
            "Promote what was shown, and nothing else",
            "Report what the trace showed",
        ]

    def test_every_step_says_when_it_is_done(self) -> None:
        for step in NARRATIVETRACE_VERIFY.steps:
            assert step.done or step.verify, step.title

    def test_renders_the_shared_reading_sections(self) -> None:
        assert NARRATIVETRACE_VERIFY.sections == (FLAVOURS, SHAPES)


class TestTheCostRuleComesFirst:
    def test_the_first_step_decides_and_a_skip_is_said_aloud(self) -> None:
        decide = NARRATIVETRACE_VERIFY.steps[0]
        assert decide.body == CommandStep(commands=())
        assert decide.done is not None
        assert "'tracing: <the reason>'" in decide.done
        assert (
            "'skipping narrativetrace-verify: <a pure function | a one-class edit with no "
            "collaborator | a flow one test already walks end to end>'"
        ) in decide.done
        assert "a skip ends the skill here, and that sentence is the report" in decide.done


class TestTheIntentComesBeforeTheRun:
    def test_the_intent_is_written_under_the_word_intent_before_the_first_traced_run(self) -> None:
        intent = _step("Write the intent down before running anything")
        assert intent.done == (
            "three to six lines in the reply, under the word Intent, written before the first "
            "traced run: which collaborators the change touches, in which order, under which "
            "branch, how many times — the oracle the trace is read against, never edited after "
            "the run"
        )

    def test_a_run_made_before_the_intent_does_not_count(self) -> None:
        run = _step("Run the smallest real path with tracing on")
        assert run.condition is not None
        assert "a trace from a run made before the Intent was written does not count" in (
            run.condition
        )
        assert run.body == SnippetStep(
            path="examples/sixty_seconds/test_place_order_flow.py", language="python"
        )
        assert (_REPO_ROOT / "examples/sixty_seconds/test_place_order_flow.py").is_file()
        assert run.verify == RUN_THE_PATH


class TestReadingTheTrace:
    def test_the_structural_trace_is_read_whole_and_every_finding_cites_a_span_id(self) -> None:
        read = _step("Read the structural trace first, against the intent")
        assert read.body == CommandStep(commands=(LIST_STRUCTURAL,))
        assert read.done is not None
        assert "read whole before any value was looked at" in read.done
        assert "naming every match and every mismatch by its span id (#2.1)" in read.done

    def test_values_and_the_fix_run_only_on_a_mismatch(self) -> None:
        for title in (
            "Open values on the span that looks wrong, and only there",
            "Fix, re-run, read again",
        ):
            assert _step(title).condition == (
                "only when the structural read named a span that does not match the intent; "
                "otherwise go on to the pin"
            )
        assert _step("Open values on the span that looks wrong, and only there").body == (
            CommandStep(commands=(LIST_NARRATIVES,))
        )


class TestThePin:
    def test_approval_mode_is_turned_on_only_when_off_and_proven_as_the_runtime_reads_it(
        self,
    ) -> None:
        on = _step("Turn approval mode on")
        assert on.condition is not None
        assert "config.approval-mode" in on.condition
        assert on.verify == APPROVAL_MODE_IS_ON
        assert on.done is not None
        assert "`approval = true` under `[tool.narrativetrace]`" in on.done
        assert "`*.received.nt`" in on.done

    def test_the_review_run_is_the_whole_suite(self) -> None:
        review = _step("Run the suite in approval mode and show every .received.nt")
        assert review.body == CommandStep(commands=(RUN_THE_SUITE_FOR_REVIEW, LIST_RECEIVED))
        assert RUN_THE_SUITE_FOR_REVIEW.startswith(RUN_THE_SUITE)

    def test_the_question_is_the_last_line_and_nothing_runs_before_the_yes(self) -> None:
        ask = _step("Ask once whether to pin it, then stop the turn")
        assert ask.body == CommandStep(commands=())
        assert ask.done == (
            "the answer is the user's next message, never something assumed in this one. "
            "Do not run narrativetrace-approve before the user says yes — promoting is the "
            "pinning. Everything else — the report, every caveat, and what promoting does — "
            "goes before the question; the question is ONE sentence ending in a question mark "
            "and it is the reply's last line, so a reply whose last line is a sentence after "
            "the question has not asked it."
        )

    def test_the_promotion_leaves_the_suite_green(self) -> None:
        promote = _step("Promote what was shown, and nothing else")
        assert promote.body == CommandStep(commands=(APPROVE,))
        assert promote.verify == RUN_THE_SUITE


class TestTheGateIsTheFeedbackSkillsOwnWording:
    """Item 7: the pin reuses the feedback skill's gate rules — the same functions, so the same
    sentences with only the artifact and the act filled in."""

    def test_the_always_rules_include_the_gate(self) -> None:
        assert (
            show_the_whole_before_asking(
                ".received.nt",
                "the baseline becomes the contract every later change is held to, and a person can "
                "only approve what they have actually read",
            )
            in NARRATIVETRACE_VERIFY.always
        )
        assert (
            end_the_turn_on_the_question(
                "Do not run narrativetrace-approve before the user says yes — promoting is the "
                "pinning."
            )
            in NARRATIVETRACE_VERIFY.always
        )

    def test_the_never_rules_include_the_gate(self) -> None:
        assert never_in_the_turn_that_asked("promote a baseline") in NARRATIVETRACE_VERIFY.never
        assert (
            never_edit_after_showing(".received.nt", "promoted", "run is rendered")
            in NARRATIVETRACE_VERIFY.never
        )

    def test_the_shared_sentences_read_as_the_feedback_skills_do(self) -> None:
        feedback = {
            rule.rule for rule in (*NARRATIVETRACE_FEEDBACK.always, *NARRATIVETRACE_FEEDBACK.never)
        }
        verify = {
            rule.rule for rule in (*NARRATIVETRACE_VERIFY.always, *NARRATIVETRACE_VERIFY.never)
        }
        assert "End the turn on the question, with nothing after it." in feedback & verify


class TestTheReport:
    def test_every_claim_cites_a_span_id_from_the_nt_that_was_read(self) -> None:
        report = _step("Report what the trace showed")
        assert report.done == (
            "two sentences on what the trace showed, every claim citing the span id it rests "
            "on — a claim without an id is not a claim, and only ids in the .nt that was read "
            "count — with the .nt attached or quoted; 'tests pass' alone is not the report"
        )


class TestTheApprovalSwitchFailureNote:
    def test_names_the_two_sources_this_runtime_refuses_rather_than_a_winner(self) -> None:
        """A narrativetrace.toml beside a [tool.narrativetrace] table raises
        DuplicateConfigurationError here — neither wins — so the note must not say one does."""
        (note,) = _step("Turn approval mode on").failure
        assert note.cause == (
            "the key sits under another table, the project also has a narrativetrace.toml (two "
            "configuration sources stop every run with DuplicateConfigurationError), or "
            "NARRATIVETRACE_APPROVAL=false is set in the environment, which wins over both"
        )
        assert note.fix == (
            "keep one source — `approval = true` directly under `[tool.narrativetrace]`, or at "
            "the top of narrativetrace.toml — unset the variable, and run the verify again"
        )
