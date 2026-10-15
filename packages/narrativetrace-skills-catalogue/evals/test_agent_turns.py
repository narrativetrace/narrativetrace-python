# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What drives a trial's agent, turn by turn. Every way of being wrong is REFUSED rather than
degraded: a multi-turn case quietly run as several unrelated single turns reaches its approval
question with an agent that forgot the draft, and passes "nothing was filed" for a reason unrelated
to the gate. Ports Java's ``AgentTurnsTest``.
"""

from __future__ import annotations

import pytest
from agent_turns import AgentTurns
from platform_presets import preset_agent_command

_SESSION = "0f8fad5b-d9cb-469f-a165-70867728950e"


class TestASingleTurnCase:
    def test_runs_the_platforms_own_preset_with_no_session(self) -> None:
        turns = AgentTurns.of("claude", "m", "s", None, "the prompt", [], _SESSION)

        assert turns.turn_count == 1
        assert turns.command_for_turn(1) == preset_agent_command("claude", "m", "s")
        assert turns.prompt_for_turn(1) == "the prompt"

    def test_an_operators_override_wins_over_the_preset(self) -> None:
        turns = AgentTurns.of("claude", "m", "s", "echo {prompt}", "p", [], _SESSION)

        assert turns.command_for_turn(1) == "echo {prompt}"

    def test_an_empty_override_falls_back_to_the_preset(self) -> None:
        assert AgentTurns.of("claude", "m", "s", "", "p", [], _SESSION).command_for_turn(1) == (
            preset_agent_command("claude", "m", "s")
        )

    def test_any_platform_can_drive_one_turn(self) -> None:
        turns = AgentTurns.of("codex", "m", "s", None, "p", [], None)

        assert turns.command_for_turn(1) == preset_agent_command("codex", "m", "s")


class TestAMultiTurnCase:
    def test_opens_under_the_trials_session_id_and_resumes_it_every_turn_after(self) -> None:
        turns = AgentTurns.of("claude", "m", "s", None, "report it", ["yes", "thanks"], _SESSION)

        assert turns.turn_count == 3
        assert turns.command_for_turn(1).endswith(f" --session-id {_SESSION}")
        assert turns.command_for_turn(2).endswith(f" --resume {_SESSION}")
        assert turns.command_for_turn(3) == turns.command_for_turn(2)
        assert [turns.prompt_for_turn(n) for n in (1, 2, 3)] == ["report it", "yes", "thanks"]

    def test_refuses_an_override_which_cannot_be_two_templates(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"\Aa multi-turn case runs on its platform's preset: one --agent-command",
        ):
            AgentTurns.of("claude", "m", "s", "echo {prompt}", "p", ["yes"], _SESSION)

    @pytest.mark.parametrize("platform", ["codex", "antigravity"])
    def test_refuses_a_platform_whose_resume_flags_were_never_verified(self, platform: str) -> None:
        with pytest.raises(ValueError, match=rf"\A{platform} cannot drive a multi-turn case"):
            AgentTurns.of(platform, "m", "s", None, "p", ["yes"], _SESSION)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "session", [None, "", "not-a-uuid", f"{_SESSION} --dangerously-skip-permissions"]
    )
    def test_refuses_a_session_id_that_is_not_one_opaque_token(self, session: str | None) -> None:
        with pytest.raises(ValueError, match=r"\Aa multi-turn trial's session id must be one"):
            AgentTurns.of("claude", "m", "s", None, "p", ["yes"], session)


class TestTheShape:
    def test_needs_at_least_one_prompt(self) -> None:
        with pytest.raises(ValueError, match=r"\Aa trial needs at least one turn's prompt\Z"):
            AgentTurns("cmd", None, ())

    @pytest.mark.parametrize("prompt", ["", "   \n"])
    def test_refuses_a_blank_prompt_in_any_turn(self, prompt: str) -> None:
        with pytest.raises(ValueError, match=r"\Aa turn with a blank prompt cannot be driven\Z"):
            AgentTurns("cmd", "resume", ("first", prompt))

    def test_several_turns_need_a_template_that_resumes(self) -> None:
        with pytest.raises(
            ValueError, match=r"\Aa trial of 2 turns needs a template that resumes its session\Z"
        ):
            AgentTurns("cmd", None, ("first", "second"))

    @pytest.mark.parametrize("turn", [0, 2, -1])
    def test_a_turn_outside_the_conversation_is_refused(self, turn: int) -> None:
        turns = AgentTurns("cmd", None, ("only",))

        with pytest.raises(ValueError, match=rf"\Aturn {turn} is outside a conversation of 1\Z"):
            turns.prompt_for_turn(turn)
        with pytest.raises(ValueError, match=rf"\Aturn {turn} is outside a conversation of 1\Z"):
            turns.command_for_turn(turn)


class TestAFreshTurn:
    """A fresh turn runs the FIRST-turn template under a session id of its own, so its agent
    remembers nothing of the install it is asked about -- the whole measurement (item 166)."""

    @staticmethod
    def _claude(replies: list[str], fresh: frozenset[int]) -> AgentTurns:
        return AgentTurns.of("claude", "m", "s", None, "turn one", replies, _SESSION, fresh)

    def test_opens_a_new_session_with_the_first_turn_template(self) -> None:
        turns = self._claude(["check my setup"], frozenset({2}))

        assert turns.command_for_turn(1).endswith(f" --session-id {_SESSION}")
        second = turns.command_for_turn(2)
        assert " --session-id " in second
        assert _SESSION not in second
        assert "--resume" not in second
        assert "{session}" not in second
        assert turns.is_fresh_turn(2) is True
        assert turns.is_fresh_turn(1) is False

    def test_two_fresh_conversations_never_share_a_session_id(self) -> None:
        first = self._claude(["check"], frozenset({2})).command_for_turn(2)
        second = self._claude(["check"], frozenset({2})).command_for_turn(2)

        assert first != second

    def test_refuses_a_fresh_turn_that_is_not_the_last_turn(self) -> None:
        with pytest.raises(ValueError, match="last turn"):
            self._claude(["check my setup", "thanks"], frozenset({2}))

    def test_refuses_a_fresh_turn_outside_the_conversation(self) -> None:
        with pytest.raises(ValueError, match="outside"):
            self._claude(["check my setup"], frozenset({3}))

    def test_refuses_turn_one_as_a_fresh_turn(self) -> None:
        with pytest.raises(ValueError, match="outside"):
            self._claude(["check my setup"], frozenset({1}))

    def test_a_platform_with_no_session_preset_refuses_it(self) -> None:
        with pytest.raises(ValueError, match="cannot drive a multi-turn case"):
            AgentTurns.of("codex", "m", "s", None, "one", ["check"], _SESSION, frozenset({2}))

    def test_a_case_with_no_fresh_turn_resumes_every_turn(self) -> None:
        turns = self._claude(["yes"], frozenset())

        assert turns.command_for_turn(2).endswith(f" --resume {_SESSION}")

    def test_a_single_turn_case_refuses_a_fresh_turn_rather_than_dropping_it(self) -> None:
        with pytest.raises(ValueError, match="outside"):
            AgentTurns.of("claude", "m", "s", None, "one", [], _SESSION, frozenset({2}))
