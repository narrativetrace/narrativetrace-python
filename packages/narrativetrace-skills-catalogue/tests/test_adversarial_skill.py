# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial tests for skill.py: edge cases, boundary conditions, unusual inputs."""

from __future__ import annotations

from narrativetrace_skills.skill import (
    Skill,
    first_token,
)


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
