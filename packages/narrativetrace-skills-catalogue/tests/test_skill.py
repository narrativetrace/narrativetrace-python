# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import pytest
from narrativetrace_skills.skill import (
    COMMAND_VOCABULARY,
    CommandStep,
    ReasonedRule,
    Skill,
    SkillSection,
    SkillStep,
    SnippetStep,
    claude_tool_pattern,
    command_strings,
    description_fits_budget,
    first_token,
    steps_without_verify,
    vocabulary_violations,
)


def _skill(**overrides: object) -> Skill:
    base: dict[str, object] = {
        "canonical_name": "demo-skill",
        "skill_class": "mechanical",
        "description": "A demo skill.",
        "fixture": "examples/demo",
        "steps": (),
        "allowed_tools": ("uv",),
    }
    base.update(overrides)
    return Skill(**base)  # type: ignore[arg-type]


class TestCommandVocabulary:
    def test_is_uv_and_git(self) -> None:
        assert COMMAND_VOCABULARY == ("uv", "git")


class TestClaudeToolPattern:
    def test_wraps_a_command_as_a_bash_tool_pattern(self) -> None:
        assert claude_tool_pattern("git") == "Bash(git *)"

    def test_wraps_the_project_wrapper_command_too(self) -> None:
        assert claude_tool_pattern("uv") == "Bash(uv *)"


class TestFirstToken:
    def test_takes_the_first_whitespace_separated_word(self) -> None:
        assert first_token("uv run pytest") == "uv"

    def test_strips_leading_whitespace(self) -> None:
        assert first_token("  git status") == "git"

    def test_empty_string_yields_empty_token(self) -> None:
        assert first_token("") == ""

    def test_whitespace_only_yields_empty_token(self) -> None:
        assert first_token("   ") == ""


class TestCommandStrings:
    def test_collects_commands_across_every_commands_step(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(title="a", body=CommandStep(commands=("uv sync",))),
                SkillStep(title="b", body=CommandStep(commands=("git status", "uv run x"))),
            )
        )
        assert command_strings(skill) == ("uv sync", "git status", "uv run x")

    def test_snippet_steps_contribute_no_commands(self) -> None:
        skill = _skill(
            steps=(SkillStep(title="a", body=SnippetStep(path="x.py", language="python")),)
        )
        assert command_strings(skill) == ()


class TestVocabularyViolations:
    def test_no_violations_for_uv_and_git_commands(self) -> None:
        skill = _skill(steps=(SkillStep(title="a", body=CommandStep(commands=("uv sync",))),))
        assert vocabulary_violations(skill) == ()

    def test_flags_a_command_outside_the_vocabulary(self) -> None:
        skill = _skill(steps=(SkillStep(title="a", body=CommandStep(commands=("npm install",))),))
        violations = vocabulary_violations(skill)
        assert violations == ("demo-skill: npm install",)


class TestDescriptionFitsBudget:
    def test_short_description_fits(self) -> None:
        assert description_fits_budget(_skill(description="short")) is True

    def test_over_budget_description_fails(self) -> None:
        assert description_fits_budget(_skill(description="x" * 1025)) is False

    def test_exactly_at_budget_fits(self) -> None:
        assert description_fits_budget(_skill(description="x" * 1024)) is True


class TestStepsWithoutVerify:
    def test_every_step_with_verify_is_excluded(self) -> None:
        skill = _skill(
            steps=(SkillStep(title="a", body=CommandStep(commands=("uv sync",)), verify="uv sync"),)
        )
        assert steps_without_verify(skill) == ()

    def test_names_a_step_missing_verify(self) -> None:
        skill = _skill(steps=(SkillStep(title="narrative only", body=CommandStep(commands=())),))
        assert steps_without_verify(skill) == ("narrative only",)

    def test_a_judgmental_step_with_a_done_condition_is_not_missing_anything(self) -> None:
        step = SkillStep(title="decide", body=CommandStep(commands=()), done="the reply says so")
        assert steps_without_verify(_skill(steps=(step,))) == ()


class TestReasonedRule:
    def test_carries_rule_and_reason(self) -> None:
        rule = ReasonedRule(rule="Never do X.", reason="because Y.")
        assert rule.rule == "Never do X."
        assert rule.reason == "because Y."


class TestSkillStepCondition:
    def test_a_step_is_unconditional_by_default(self) -> None:
        assert SkillStep(title="a", body=CommandStep(commands=("uv sync",))).condition is None

    def test_a_condition_is_kept(self) -> None:
        step = SkillStep(title="a", body=CommandStep(commands=()), condition="if x")
        assert step.condition == "if x"

    @pytest.mark.parametrize("blank", ["", " ", "\n\t"])
    def test_a_blank_condition_is_rejected(self, blank: str) -> None:
        with pytest.raises(
            ValueError, match=r"\Aa SkillStep's condition must not be blank when present\Z"
        ):
            SkillStep(title="a", body=CommandStep(commands=()), condition=blank)


class TestSkillSection:
    """A named block of reference text rendered after the steps — written once in the catalogue
    and rendered into every skill that lists it."""

    def test_heading_and_markdown_are_kept(self) -> None:
        section = SkillSection(heading="Shapes", markdown="- a call made twice\n")
        assert (section.heading, section.markdown) == ("Shapes", "- a call made twice\n")

    @pytest.mark.parametrize("blank", ["", " ", "\n"])
    def test_a_blank_heading_is_rejected(self, blank: str) -> None:
        with pytest.raises(ValueError, match=r"\Aa SkillSection's heading must not be blank\Z"):
            SkillSection(heading=blank, markdown="x")

    @pytest.mark.parametrize("heading", ["two\nlines", "carriage\rreturn", "# a heading"])
    def test_a_heading_is_one_line_of_text_not_markdown(self, heading: str) -> None:
        with pytest.raises(
            ValueError, match=r"\Aa SkillSection's heading is one line of text, not markdown: "
        ):
            SkillSection(heading=heading, markdown="x")

    @pytest.mark.parametrize("blank", ["", "  \n"])
    def test_blank_markdown_is_rejected(self, blank: str) -> None:
        with pytest.raises(ValueError, match=r"\Aa SkillSection's markdown must not be blank\Z"):
            SkillSection(heading="h", markdown=blank)

    def test_a_skill_carries_no_sections_by_default(self) -> None:
        assert _skill().sections == ()


class TestSkillStepDone:
    """The prose done-condition of a judgmental step — what the reply must show — kept apart from
    ``verify``, which in this catalogue is always a runnable command."""

    def test_a_step_has_no_done_condition_by_default(self) -> None:
        assert SkillStep(title="a", body=CommandStep(commands=())).done is None

    @pytest.mark.parametrize("blank", ["", " ", "\n\t"])
    def test_a_blank_done_condition_is_rejected(self, blank: str) -> None:
        with pytest.raises(
            ValueError, match=r"\Aa SkillStep's done condition must not be blank when present\Z"
        ):
            SkillStep(title="a", body=CommandStep(commands=()), done=blank)


class TestAdversarialSchemaEdges:
    @pytest.mark.parametrize("blank", ["", " ", "\n"])
    def test_a_blank_verify_is_rejected_not_rendered_as_no_proof(self, blank: str) -> None:
        with pytest.raises(
            ValueError, match=r"\Aa SkillStep's verify must not be blank when present\Z"
        ):
            SkillStep(title="a", body=CommandStep(commands=()), verify=blank)

    @pytest.mark.parametrize("separator", ["\u2028", "\u2029"])
    def test_a_heading_with_a_unicode_line_separator_is_not_one_line(self, separator: str) -> None:
        with pytest.raises(ValueError, match=r"\Aa SkillSection's heading is one line of text"):
            SkillSection(heading=f"Shapes{separator}# injected", markdown="x")
