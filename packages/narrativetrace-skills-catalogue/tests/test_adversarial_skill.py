# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial tests for skill.py: edge cases, boundary conditions, unusual inputs."""

from __future__ import annotations

from narrativetrace_skills.skill import (
    Skill,
    claude_tool_pattern,
    first_token,
)


class TestClaudeToolPatternAdversarial:
    """Edge cases and boundary conditions for claude_tool_pattern."""

    def test_empty_string_command(self) -> None:
        # Empty command should still be wrapped
        result = claude_tool_pattern("")
        assert result == "Bash( *)"

    def test_command_with_parentheses(self) -> None:
        # Command with parentheses in its name (hypothetical, but adversarial)
        result = claude_tool_pattern("git(flow)")
        assert result == "Bash(git(flow) *)"

    def test_command_with_special_characters(self) -> None:
        # Command with dashes and numbers
        result = claude_tool_pattern("uv-2.0")
        assert result == "Bash(uv-2.0 *)"

    def test_command_with_unicode(self) -> None:
        # Unicode characters in command name (unlikely but adversarial)
        result = claude_tool_pattern("gît")
        assert result == "Bash(gît *)"

    def test_command_with_trailing_spaces(self) -> None:
        # Trailing spaces should be included as-is (no strip)
        result = claude_tool_pattern("git  ")
        assert result == "Bash(git   *)"

    def test_command_with_leading_spaces(self) -> None:
        # Leading spaces should be included
        result = claude_tool_pattern("  git")
        assert result == "Bash(  git *)"


class TestFirstTokenAdversarial:
    """Edge cases for first_token."""

    def test_single_word_no_whitespace(self) -> None:
        assert first_token("git") == "git"

    def test_tab_separated(self) -> None:
        assert first_token("git\tstatus") == "git"

    def test_multiple_spaces_between_tokens(self) -> None:
        assert first_token("git    status") == "git"

    def test_mixed_whitespace(self) -> None:
        assert first_token("  \t  git") == "git"

    def test_trailing_whitespace_only(self) -> None:
        assert first_token("git  ") == "git"


class TestSkillWithEmptyAllowedTools:
    """Skill with empty allowed_tools tuple."""

    def test_skill_with_no_allowed_tools(self) -> None:
        skill = Skill(
            canonical_name="test-skill",
            skill_class="mechanical",
            description="A test skill.",
            fixture="examples/test",
            steps=(),
            allowed_tools=(),
        )
        assert skill.allowed_tools == ()

    def test_skill_with_tool_containing_whitespace(self) -> None:
        # A tool name with internal whitespace (adversarial)
        skill = Skill(
            canonical_name="test-skill",
            skill_class="mechanical",
            description="A test skill.",
            fixture="examples/test",
            steps=(),
            allowed_tools=("u v",),
        )
        assert "u v" in skill.allowed_tools
