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
    preset_first_turn_command,
    preset_resumed_turn_command,
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
    def test_claude_grants_the_tools_the_published_prompt_implies(self) -> None:
        command = preset_agent_command("claude", "haiku", "narrativetrace-doctor")
        assert command == (
            'claude -p "{prompt}" --model haiku '
            '--allowed-tools "Bash,Read,Edit,Write,WebFetch,Skill" '
            "--output-format stream-json --verbose --strict-mcp-config"
        )

    def test_claude_streams_its_tool_calls_for_the_grader_to_read(self) -> None:
        """A grader reads the agent's TOOL CALLS, not only its closing text: a URL a command
        printed and a URL typed into a reply are the same event to a gate that must see neither
        before the user's approval turn. ``--verbose`` is not decoration -- without it this CLI
        exits 1 having written nothing at all (Java, verified 2026-10-05)."""
        command = preset_agent_command("claude", "haiku", "narrativetrace-feedback")
        assert "--output-format stream-json --verbose" in command

    def test_claude_loads_no_account_connector(self) -> None:
        """The seeded login brings the ACCOUNT's connectors (mail, drive, calendar -- write tools
        among them) into a fresh configuration; verified in this container 2026-10-08, where
        ``--strict-mcp-config`` with no ``--mcp-config`` left ``mcp_servers: []`` across a resume.
        A network path no PATH stand-in covers is not contained."""
        command = preset_agent_command("claude", "haiku", "narrativetrace-feedback")
        assert command.endswith(" --strict-mcp-config")

    def test_claude_may_invoke_a_skill(self) -> None:
        """Step 4 of the published prompt opens "if the `add-narrative-tracing` skill is now
        available, follow it" -- and a REGISTRY case whose agent cannot invoke a skill measures
        nothing the registry delivered. Same class of defect as a preset that grants no WebFetch
        against a prompt whose step 1 is to read a URL."""
        assert "Skill" in preset_agent_command("claude", "haiku", "add-narrative-tracing")

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


class TestMultiTurnPresets:
    def test_claude_opens_a_conversation_under_the_trials_own_session_id(self) -> None:
        assert preset_first_turn_command("claude", "m", "s") == (
            preset_agent_command("claude", "m", "s") + " --session-id {session}"
        )

    def test_claude_resumes_that_same_conversation_rather_than_forking_it(self) -> None:
        assert preset_resumed_turn_command("claude", "m", "s") == (
            preset_agent_command("claude", "m", "s") + " --resume {session}"
        )

    def test_a_platform_whose_resume_flags_were_never_verified_has_neither_half(self) -> None:
        """Both halves empty, never one: a platform that could open a conversation but not resume
        it would run its "second turn" as a fresh session with no memory of the draft, where
        "nothing was filed" is true for a reason unrelated to the gate."""
        for platform in SPORADIC_PLATFORMS:
            assert preset_first_turn_command(platform, "m", "s") is None
            assert preset_resumed_turn_command(platform, "m", "s") is None
