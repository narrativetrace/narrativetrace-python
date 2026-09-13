# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from platform_presets import (
    PLATFORMS,
    SPORADIC_PLATFORMS,
    is_platform,
    is_read_only_skill,
    is_sporadic_platform,
    preset_agent_command,
)


class TestPlatforms:
    def test_three_platforms(self) -> None:
        assert PLATFORMS == ("claude", "codex", "gemini")

    def test_is_platform_accepts_known_names(self) -> None:
        assert is_platform("claude") is True
        assert is_platform("codex") is True

    def test_is_platform_rejects_unknown_names(self) -> None:
        assert is_platform("chatgpt") is False


class TestSporadicPlatforms:
    def test_codex_and_gemini_are_sporadic(self) -> None:
        assert SPORADIC_PLATFORMS == frozenset({"codex", "gemini"})

    def test_claude_is_not_sporadic(self) -> None:
        assert is_sporadic_platform("claude") is False

    def test_codex_is_sporadic(self) -> None:
        assert is_sporadic_platform("codex") is True


class TestIsReadOnlySkill:
    def test_the_doctor_skill_is_read_only(self) -> None:
        assert is_read_only_skill("narrativetrace-doctor") is True

    def test_every_other_skill_is_not(self) -> None:
        assert is_read_only_skill("add-narrative-tracing") is False


class TestPresetAgentCommand:
    def test_claude_uses_the_p_flag_and_allowed_tools(self) -> None:
        command = preset_agent_command("claude", "haiku", "narrativetrace-doctor")
        assert command == 'claude -p "{prompt}" --model haiku --allowed-tools Bash'

    def test_codex_uses_read_only_sandbox_for_the_doctor_skill(self) -> None:
        command = preset_agent_command("codex", "mini", "narrativetrace-doctor")
        assert "--sandbox read-only" in command

    def test_codex_uses_workspace_write_sandbox_for_a_mutating_skill(self) -> None:
        command = preset_agent_command("codex", "mini", "add-narrative-tracing")
        assert "--sandbox workspace-write" in command

    def test_gemini_uses_plan_approval_mode_for_the_doctor_skill(self) -> None:
        command = preset_agent_command("gemini", "flash", "narrativetrace-doctor")
        assert "--approval-mode plan" in command

    def test_gemini_uses_auto_edit_approval_mode_for_a_mutating_skill(self) -> None:
        command = preset_agent_command("gemini", "flash", "add-narrative-tracing")
        assert "--approval-mode auto_edit" in command
