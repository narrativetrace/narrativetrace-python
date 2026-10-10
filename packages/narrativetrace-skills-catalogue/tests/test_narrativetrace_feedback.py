# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ``narrativetrace-feedback`` skill: the only catalogue skill that can publish something."""

from __future__ import annotations

import dataclasses

from narrativetrace_skills import (
    SKILLS,
    command_strings,
    find_skill,
    publishing_not_pre_approved,
    render_claude_skill,
    render_codex_skill,
)
from narrativetrace_skills.catalogue.narrativetrace_doctor import NARRATIVETRACE_DOCTOR
from narrativetrace_skills.catalogue.narrativetrace_feedback import NARRATIVETRACE_FEEDBACK


def _resolve(path: str) -> str:
    raise AssertionError(f"this skill embeds no snippet, asked for {path}")


class TestNarrativetraceFeedback:
    def test_is_in_the_catalogue_under_its_canonical_name(self) -> None:
        assert find_skill("narrativetrace-feedback") is NARRATIVETRACE_FEEDBACK
        assert NARRATIVETRACE_FEEDBACK in SKILLS

    def test_declares_no_pre_approved_tool(self) -> None:
        assert NARRATIVETRACE_FEEDBACK.allowed_tools == ()

    def test_the_real_catalogue_pre_approves_no_publishing_command(self) -> None:
        assert publishing_not_pre_approved(SKILLS) == ()

    def test_the_skill_does_run_the_publishing_verb(self) -> None:
        # Without this the lint above passes vacuously: it only bites on a skill that names the
        # verb, and a rename of the verb would leave it green and guarding nothing.
        verbs = [
            c for c in command_strings(NARRATIVETRACE_FEEDBACK) if "narrativetrace feedback" in c
        ]
        assert len(verbs) >= 2

    def test_the_lint_would_catch_this_skill_if_it_ever_declared_uv(self) -> None:
        # The probe that the lint above can fail on the REAL skill: the draft command, the URL
        # commands, the draft display and both verifies each name the publishing verb or its output
        # directory -- the lint is deliberately conservative: it keys on the word.
        declared = dataclasses.replace(NARRATIVETRACE_FEEDBACK, allowed_tools=("uv",))
        violations = publishing_not_pre_approved((declared,))
        assert len(violations) == 5
        assert all(
            v.startswith('narrativetrace-feedback: declares allowed tool "uv"') for v in violations
        )

    def test_claude_page_has_no_allowed_tools_line(self) -> None:
        assert "allowed-tools" not in render_claude_skill(NARRATIVETRACE_FEEDBACK, _resolve)

    def test_no_step_runs_gh(self) -> None:
        # `gh` is the verb's third channel: printed for the user, never run by the skill.
        assert not [c for c in command_strings(NARRATIVETRACE_FEEDBACK) if c.startswith("gh")]

    def test_both_flavours_carry_the_stop_the_turn_step_without_a_fence(self) -> None:
        for page in (
            render_claude_skill(NARRATIVETRACE_FEEDBACK, _resolve),
            render_codex_skill(NARRATIVETRACE_FEEDBACK, _resolve),
        ):
            assert "## 4. Ask once whether to file it, then stop the turn\n\n## 5." in page


class TestDoctorPointsAtTheFeedbackSkill:
    def test_the_doctors_closing_always_rule_names_the_skill_exactly(self) -> None:
        pointers = [r for r in NARRATIVETRACE_DOCTOR.always if "narrativetrace-feedback" in r.rule]
        assert [r.rule for r in pointers] == [
            "If a check is wrong, or its fix does not work, report it with the "
            "narrativetrace-feedback skill."
        ]
        assert NARRATIVETRACE_DOCTOR.always[-1] is pointers[0]

    def test_the_pointer_says_why_and_that_nothing_is_filed_without_an_answer(self) -> None:
        assert NARRATIVETRACE_DOCTOR.always[-1].reason == (
            "a wrong finding costs every project that hits it until somebody says so, and that "
            "skill shows you the whole report and files nothing without your answer"
        )

    def test_the_doctor_stays_read_only_and_pre_approves_no_publishing_command(self) -> None:
        assert not any("feedback" in c for c in command_strings(NARRATIVETRACE_DOCTOR))
