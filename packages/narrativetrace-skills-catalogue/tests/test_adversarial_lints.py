# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial tests for lints.py: edge cases for allowed_tools_violations and other lints."""

from __future__ import annotations

from narrativetrace_skills.lints import allowed_tools_violations, unparseable_commands
from narrativetrace_skills.skill import CommandStep, Skill, SkillStep


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


class TestAllowedToolsViolationsAdversarial:
    """Adversarial edge cases for allowed_tools_violations."""

    def test_empty_string_in_allowed_tools(self) -> None:
        skill = _skill(allowed_tools=("",))
        violations = allowed_tools_violations((skill,))
        assert len(violations) == 1
        assert "outside the vocabulary" in violations[0]

    def test_multiple_violations_in_single_skill(self) -> None:
        skill = _skill(allowed_tools=("npm", "docker", "uv"))
        violations = allowed_tools_violations((skill,))
        # Should flag npm and docker but not uv
        assert len(violations) == 2
        assert any("npm" in v for v in violations)
        assert any("docker" in v for v in violations)

    def test_tool_with_nested_parentheses(self) -> None:
        skill = _skill(allowed_tools=("Bash(git (flow) *)",))
        violations = allowed_tools_violations((skill,))
        assert len(violations) == 1
        assert "rendered platform spelling" in violations[0]

    def test_tool_with_only_opening_paren(self) -> None:
        skill = _skill(allowed_tools=("Bash(git",))
        violations = allowed_tools_violations((skill,))
        assert len(violations) == 1
        assert "rendered platform spelling" in violations[0]

    def test_tool_with_unicode(self) -> None:
        skill = _skill(allowed_tools=("gît",))
        violations = allowed_tools_violations((skill,))
        # Should flag as outside vocabulary, not as rendered spelling
        assert len(violations) == 1
        assert "outside the vocabulary" in violations[0]

    def test_tool_with_numbers_and_dashes(self) -> None:
        # Vocabulary command-like names with numbers/dashes
        skill = _skill(allowed_tools=("uv-2.0",))
        violations = allowed_tools_violations((skill,))
        # Not in vocabulary, so should be flagged
        assert len(violations) == 1
        assert "outside the vocabulary" in violations[0]

    def test_mixed_valid_and_invalid_tools(self) -> None:
        skill = _skill(allowed_tools=("uv", "git", "npm", "docker"))
        violations = allowed_tools_violations((skill,))
        # Only npm and docker are invalid
        assert len(violations) == 2

    def test_tool_that_is_part_of_a_pattern_but_not_exact(self) -> None:
        # "git" is valid, but "git-flow" is not
        skill = _skill(allowed_tools=("git-flow",))
        violations = allowed_tools_violations((skill,))
        assert len(violations) == 1
        assert "outside the vocabulary" in violations[0]


class TestUnparseableCommandsAdversarial:
    """Adversarial edge cases for unparseable_commands."""

    def test_command_with_only_tabs(self) -> None:
        skill = _skill(steps=(SkillStep(title="s", body=CommandStep(commands=("\t\t",))),))
        violations = unparseable_commands((skill,))
        assert len(violations) == 1

    def test_command_with_null_bytes(self) -> None:
        # Null byte would terminate the token early
        skill = _skill(steps=(SkillStep(title="s", body=CommandStep(commands=("uv\x00sync",))),))
        violations = unparseable_commands((skill,))
        # Should not flag this as unparseable; first_token("uv\x00sync") == "uv"
        assert len(violations) == 0

    def test_multiple_unparseable_commands_in_one_step(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(title="s", body=CommandStep(commands=("   ", "\t", "uv sync", "  \t  "))),
            )
        )
        violations = unparseable_commands((skill,))
        # Three empty ones, but uv sync is valid
        assert len(violations) == 3
