# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace_skills.skill import (
    COMMAND_VOCABULARY,
    CommandStep,
    ReasonedRule,
    Skill,
    SkillStep,
    SnippetStep,
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


class TestReasonedRule:
    def test_carries_rule_and_reason(self) -> None:
        rule = ReasonedRule(rule="Never do X.", reason="because Y.")
        assert rule.rule == "Never do X."
        assert rule.reason == "because Y."
