# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace-debug`` — Phase 7 D4's loop from a symptom, the shared reading sections rendered
(not copied), the shared pin, and the hand-off to ``narrativetrace-feedback``."""

from __future__ import annotations

from narrativetrace_skills.catalogue import baseline_pin
from narrativetrace_skills.catalogue.debug_commands import LIST_DIAGRAMS, REPRODUCE
from narrativetrace_skills.catalogue.narrativetrace_debug import NARRATIVETRACE_DEBUG
from narrativetrace_skills.catalogue.narrativetrace_verify import FLOW_TEST, NARRATIVETRACE_VERIFY
from narrativetrace_skills.catalogue.verify_commands import LIST_NARRATIVES, LIST_STRUCTURAL
from narrativetrace_skills.catalogue_index import SKILLS
from narrativetrace_skills.lints import promotion_not_pre_approved
from narrativetrace_skills.skill import CommandStep, SkillStep, SnippetStep


def _step(title: str) -> SkillStep:
    return next(step for step in NARRATIVETRACE_DEBUG.steps if step.title == title)


def _titles() -> list[str]:
    return [step.title for step in NARRATIVETRACE_DEBUG.steps]


class TestShape:
    def test_is_in_the_catalogue_once(self) -> None:
        assert [s.canonical_name for s in SKILLS].count("narrativetrace-debug") == 1

    def test_is_a_guided_skill_that_declares_no_allowed_tools(self) -> None:
        assert NARRATIVETRACE_DEBUG.skill_class == "guided"
        assert NARRATIVETRACE_DEBUG.allowed_tools == ()
        assert promotion_not_pre_approved((NARRATIVETRACE_DEBUG,)) == ()

    def test_the_loop_then_the_pin_then_the_report(self) -> None:
        assert _titles() == [
            "Reproduce the symptom with tracing on",
            "Find the symptom in the values",
            "Across threads, read the sequence diagram first",
            "Localize by reading: name the first span where a value diverges",
            "Bisect by span, not by file",
            "Hand a defect in NarrativeTrace itself to narrativetrace-feedback",
            "Fix it in the diverging span, re-run the same input, read the same span",
            "Check that nothing else moved",
            "Keep the reproduction as the regression test",
            *[step.title for step in baseline_pin.STEPS],
            "Report the root cause as the trace showed it",
        ]

    def test_every_step_says_when_it_is_done(self) -> None:
        for step in NARRATIVETRACE_DEBUG.steps:
            assert step.done or step.verify, step.title


class TestSharedWithVerify:
    """Item 7 of milestone 2: two skills share one listing, one reading text and one pin."""

    def test_both_skills_render_the_same_reading_sections(self) -> None:
        assert NARRATIVETRACE_DEBUG.sections == NARRATIVETRACE_VERIFY.sections
        assert all(
            ours is theirs
            for ours, theirs in zip(
                NARRATIVETRACE_DEBUG.sections, NARRATIVETRACE_VERIFY.sections, strict=True
            )
        )

    def test_both_skills_carry_the_same_pin_steps_and_rules(self) -> None:
        for skill in (NARRATIVETRACE_DEBUG, NARRATIVETRACE_VERIFY):
            assert all(step in skill.steps for step in baseline_pin.STEPS)
            assert all(rule in skill.always for rule in baseline_pin.ALWAYS)
            assert all(rule in skill.never for rule in baseline_pin.NEVER)

    def test_both_reproduce_on_the_same_listing(self) -> None:
        reproduce = _step("Reproduce the symptom with tracing on")
        assert reproduce.body == SnippetStep(path=FLOW_TEST, language="python")
        assert reproduce.verify == REPRODUCE


class TestReadingBeforeChanging:
    def test_the_diverging_span_is_named_by_id_before_any_code_changes(self) -> None:
        localize = _step("Localize by reading: name the first span where a value diverges")
        assert localize.body == CommandStep(commands=())
        assert localize.done is not None
        assert "names that span by its id (#1.3)" in localize.done
        assert "before any code is changed: by reading, not by stepping" in localize.done
        assert _titles().index(localize.title) < _titles().index(
            "Fix it in the diverging span, re-run the same input, read the same span"
        )

    def test_the_symptom_is_found_in_the_values(self) -> None:
        symptom = _step("Find the symptom in the values")
        assert symptom.body == CommandStep(commands=(LIST_NARRATIVES,))

    def test_the_diagram_comes_first_only_across_threads_or_for_order(self) -> None:
        diagram = _step("Across threads, read the sequence diagram first")
        assert diagram.body == CommandStep(commands=(LIST_DIAGRAMS,))
        assert diagram.condition is not None
        assert "a fork, async or fire-and-forget marker" in diagram.condition


class TestNarrowingNeverRedacts:
    """Item 2 of milestone 2: this port's not-traced marker REDACTS, so it never narrows."""

    def test_bisect_wraps_one_more_collaborator_and_forbids_the_redaction_marker(self) -> None:
        bisect = _step("Bisect by span, not by file")
        assert bisect.body == CommandStep(commands=(REPRODUCE,))
        assert bisect.done is not None
        assert "wrapped with trace_object" in bisect.done
        assert (
            "never not_traced_field, __nt_not_traced__ or @not_traced to narrow — in Python they "
            "redact a value, they do not scope a trace"
        ) in bisect.done


class TestTheFixIsWhereItDiverged:
    def test_a_fix_elsewhere_is_undone(self) -> None:
        fix = _step("Fix it in the diverging span, re-run the same input, read the same span")
        assert fix.verify == REPRODUCE
        assert fix.done is not None
        assert "a change anywhere else that makes the test pass silences the symptom" in fix.done

    def test_the_shape_before_the_fix_comes_from_the_red_runs_markdown(self) -> None:
        """Item 3 of milestone 2: a red run here writes the .md and .mmd but no .nt."""
        delta = _step("Check that nothing else moved")
        assert delta.body == CommandStep(commands=(LIST_STRUCTURAL,))
        assert delta.done is not None
        assert "a red run writes no .nt (the .nt on disk is the last green one)" in delta.done


class TestHandOffAndReport:
    def test_a_defect_in_narrativetrace_goes_to_feedback_without_values(self) -> None:
        hand_off = _step("Hand a defect in NarrativeTrace itself to narrativetrace-feedback")
        assert hand_off.condition is not None
        assert hand_off.done is not None
        assert "never a value from the trace" in hand_off.done
        assert _titles().index(hand_off.title) < _titles().index(
            "Fix it in the diverging span, re-run the same input, read the same span"
        )

    def test_the_report_comes_before_the_pin_question_and_the_id_again_after(self) -> None:
        """Item 4 of milestone 2: the gate puts the report before the question."""
        report = _step("Report the root cause as the trace showed it")
        assert report.done is not None
        assert "The report is written in full before the pin question" in report.done
        assert "names the span id again in its one-line summary of the cause" in report.done
