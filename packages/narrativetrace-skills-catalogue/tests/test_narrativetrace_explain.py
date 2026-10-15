# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace-explain`` — the loop for a user who has not thought of tracing: decide whether
the source already answers, choose one scenario, run it as found, read the shape, explain by span
id. Renders the same reading sections verify and debug do, and declares no allowed tools."""

from __future__ import annotations

from narrativetrace_skills.catalogue.explain_commands import RUN_THE_SCENARIO
from narrativetrace_skills.catalogue.narrativetrace_debug import NARRATIVETRACE_DEBUG
from narrativetrace_skills.catalogue.narrativetrace_explain import (
    FROM_THE_SOURCE,
    NARRATIVETRACE_EXPLAIN,
    ONLY_WHAT_THE_QUESTION_NEEDS,
)
from narrativetrace_skills.catalogue.trace_reading import (
    FLAVOURS,
    NEVER_REDACTION_OFF,
    SHAPES,
)
from narrativetrace_skills.catalogue.verify_commands import LIST_NARRATIVES, LIST_STRUCTURAL
from narrativetrace_skills.catalogue_index import SKILLS
from narrativetrace_skills.lints import promotion_not_pre_approved
from narrativetrace_skills.skill import CommandStep, SkillStep

_DECIDE = "Decide whether the source already answers it, and say so"
_SCENARIO = "Choose the one scenario that already exercises the flow"
_INSTALL = "Install tracing first when the project has none"
_RUN = "Run that one scenario with tracing on"
_SHAPE = "Read the structural trace first, in the order it ran"
_VALUES = "Open values only where the question needs one"
_HAND_OFF = "Hand off when it stops being an explanation"
_EXPLAIN = "Explain the run by span id, and mark what you inferred"


def _step(title: str) -> SkillStep:
    return next(step for step in NARRATIVETRACE_EXPLAIN.steps if step.title == title)


def _titles() -> list[str]:
    return [step.title for step in NARRATIVETRACE_EXPLAIN.steps]


class TestShape:
    def test_ships_in_the_catalogue_right_after_the_debug_skill(self) -> None:
        names = [skill.canonical_name for skill in SKILLS]
        assert names.count("narrativetrace-explain") == 1
        assert names.index("narrativetrace-explain") == names.index("narrativetrace-debug") + 1
        assert SKILLS[names.index("narrativetrace-explain")] is NARRATIVETRACE_EXPLAIN

    def test_is_guided_and_declares_no_allowed_tools(self) -> None:
        assert NARRATIVETRACE_EXPLAIN.skill_class == "guided"
        assert NARRATIVETRACE_EXPLAIN.allowed_tools == ()
        assert promotion_not_pre_approved((NARRATIVETRACE_EXPLAIN,)) == ()

    def test_the_eight_steps_in_order(self) -> None:
        assert _titles() == [
            _DECIDE,
            _SCENARIO,
            _INSTALL,
            _RUN,
            _SHAPE,
            _VALUES,
            _HAND_OFF,
            _EXPLAIN,
        ]

    def test_every_step_says_when_it_is_done(self) -> None:
        assert all(step.done and step.done.strip() for step in NARRATIVETRACE_EXPLAIN.steps)

    def test_it_is_a_reading_loop_so_the_only_commands_are_the_run_and_two_listings(self) -> None:
        commands = [
            command
            for step in NARRATIVETRACE_EXPLAIN.steps
            if isinstance(step.body, CommandStep)
            for command in step.body.commands
        ]
        assert commands == [RUN_THE_SCENARIO, LIST_STRUCTURAL, LIST_NARRATIVES]
        assert not any("approve" in command or "init" in command for command in commands)


class TestCostRule:
    def test_the_first_step_decides_and_ends_the_skill_when_the_source_answers(self) -> None:
        first = NARRATIVETRACE_EXPLAIN.steps[0]
        assert first.body == CommandStep(commands=())
        assert first.done is not None
        for words in (
            "before anything is installed or run",
            "'reading the source: <the reason>'",
            "'tracing: <the reason>'",
            "with no install and no run",
            "the skill ends there",
        ):
            assert words in first.done

    def test_the_cost_rule_is_an_always_rule_that_carries_its_reason(self) -> None:
        assert FROM_THE_SOURCE in NARRATIVETRACE_EXPLAIN.always
        assert FROM_THE_SOURCE.rule == (
            "Answer from the source when ten lines of source answer the question"
        )
        assert "cost the user time and tokens" in FROM_THE_SOURCE.reason
        assert "where the path is not obvious" in FROM_THE_SOURCE.reason


class TestTheLoop:
    def test_one_scenario_is_chosen_and_a_new_one_written_only_where_none_exists(self) -> None:
        scenario = _step(_SCENARIO)
        assert scenario.done is not None
        for words in ("names ONE scenario", "an existing test", "written only where"):
            assert words in scenario.done
        assert "Two scenarios is two traces" in scenario.done

    def test_an_uninstalled_project_is_routed_through_the_install_skill_before_the_run(
        self,
    ) -> None:
        install = _step(_INSTALL)
        assert install.condition is not None
        assert "only when the project has no NarrativeTrace at all" in install.condition
        assert "go straight to the run" in install.condition
        assert install.done is not None
        assert "add-narrative-tracing" in install.done
        assert "does not refactor" in install.done
        assert _titles().index(_INSTALL) < _titles().index(_RUN)

    def test_the_run_drives_the_scenario_as_found_and_routes_to_the_doctor_on_silence(
        self,
    ) -> None:
        run = _step(_RUN)
        assert run.body == CommandStep(commands=(RUN_THE_SCENARIO,))
        assert run.done is not None
        assert "a run that writes nothing is the failure below" in run.done
        assert "ran as it was found" in run.done
        assert run.condition is not None
        assert "run that one, as it is" in run.condition
        assert len(run.failure) == 1
        assert "narrativetrace-doctor" in run.failure[0].fix

    def test_the_structure_is_read_whole_and_by_span_id(self) -> None:
        shape = _step(_SHAPE)
        assert shape.body == CommandStep(commands=(LIST_STRUCTURAL,))
        assert shape.done is not None
        assert "read whole before any value" in shape.done
        assert "by span id" in shape.done

    def test_values_are_opened_after_the_structure_and_only_where_the_question_needs_one(
        self,
    ) -> None:
        values = _step(_VALUES)
        assert values.body == CommandStep(commands=(LIST_NARRATIVES,))
        assert values.condition == ONLY_WHAT_THE_QUESTION_NEEDS
        assert values.done is not None
        assert "not the whole file" in values.done
        assert "[REDACTED]" in values.done
        assert _titles().index(_VALUES) == _titles().index(_SHAPE) + 1

    def test_a_defect_or_a_change_in_progress_is_handed_off_not_fixed_here(self) -> None:
        hand_off = _step(_HAND_OFF)
        assert hand_off.condition is not None
        assert "only when the run shows something wrong" in hand_off.condition
        assert "a change of this session's own" in hand_off.condition
        assert hand_off.done is not None
        for words in ("narrativetrace-debug", "narrativetrace-verify", "fixes nothing itself"):
            assert words in hand_off.done
        assert _titles().index(_SHAPE) < _titles().index(_HAND_OFF) < _titles().index(_EXPLAIN)

    def test_the_last_step_explains_by_span_id_and_names_what_was_not_observed(self) -> None:
        last = NARRATIVETRACE_EXPLAIN.steps[-1]
        assert last.title == _EXPLAIN
        assert last.done is not None
        for words in (
            "in the user's own words",
            "citing the span id it rests on",
            "a claim without an id is not a claim",
            "marked as an inference",
            "what was NOT observed",
        ):
            assert words in last.done


class TestSharedAndRules:
    def test_it_renders_the_very_reading_sections_verify_and_debug_render(self) -> None:
        assert NARRATIVETRACE_EXPLAIN.sections == (FLAVOURS, SHAPES)
        assert all(
            ours is theirs
            for ours, theirs in zip(
                NARRATIVETRACE_EXPLAIN.sections, NARRATIVETRACE_DEBUG.sections, strict=True
            )
        )

    def test_the_rules_forbid_inventing_observations_and_changing_code_to_explain_it(self) -> None:
        always = [rule.rule for rule in NARRATIVETRACE_EXPLAIN.always]
        never = [rule.rule for rule in NARRATIVETRACE_EXPLAIN.never]
        assert always == [
            FROM_THE_SOURCE.rule,
            "Cite a span id for every claim about the trace.",
            "Separate what the trace showed from what you inferred.",
        ]
        assert never == [
            "Never present an unobserved call as something the trace showed.",
            "Never change the code in order to explain it.",
            NEVER_REDACTION_OFF.rule,
        ]
        assert NEVER_REDACTION_OFF in NARRATIVETRACE_EXPLAIN.never

    def test_the_description_carries_the_questions_a_user_asks(self) -> None:
        description = NARRATIVETRACE_EXPLAIN.description
        for words in (
            "'show me what my application actually does'",
            "'walk me through what happens when a user checks out'",
            "'I inherited this service, how does an order flow'",
            "'what does this endpoint call'",
            "nothing broken and no change needing verification",
            "BEFORE reading source files",
            "add-narrative-tracing",
            "narrativetrace-debug",
            "narrativetrace-verify",
        ):
            assert words in description
        assert NARRATIVETRACE_EXPLAIN.when_to_use is not None
        assert NARRATIVETRACE_EXPLAIN.when_to_use.startswith("Non-obvious triggers")
