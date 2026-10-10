# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""INTENT: everything that drives a trial's agent -- one command template per turn, one prompt per
turn, and the session id that makes several turns ONE conversation. Ports Java's ``AgentTurns``.

A single-turn trial is the ordinary shape: one prompt, the platform's preset or the operator's
``--agent-command``, no session. A multi-turn trial is the shape a case needs when what it
measures must happen in a LATER turn than the one that asked -- an approval is only an approval if
it arrives in a turn of the user's own.

**@llmNote** Every way of being wrong is REFUSED here rather than degraded, and that is the
load-bearing decision in this type. A multi-turn case quietly run as several independent single
turns would reach its approval question with an agent that had forgotten the draft, and then pass
its grader -- "nothing was filed" -- for a reason that has nothing to do with the gate.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from platform_presets import (
    SESSION_PLACEHOLDER,
    Platform,
    preset_agent_command,
    preset_first_turn_command,
    preset_resumed_turn_command,
)

_SESSION_ID: Final = re.compile(r"\A[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
"""One opaque token: an id carrying whitespace or a quote would split into two argv elements and
silently change the command it was spliced into."""


@dataclass(frozen=True, slots=True)
class AgentTurns:
    """``first_turn_command`` drives turn 1; ``resumed_turn_command`` every turn after it (``None``
    for one turn); ``prompts`` is ``prompt.md`` then the case's scripted replies, in turn order."""

    first_turn_command: str
    resumed_turn_command: str | None
    prompts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.prompts:
            raise ValueError("a trial needs at least one turn's prompt")
        if any(not prompt.strip() for prompt in self.prompts):
            raise ValueError("a turn with a blank prompt cannot be driven")
        if len(self.prompts) > 1 and not self.resumed_turn_command:
            raise ValueError(
                f"a trial of {len(self.prompts)} turns needs a template that resumes its session"
            )

    @classmethod
    def of(  # noqa: PLR0913 - mirrors the runner's own inputs one to one
        cls,
        platform: Platform,
        model: str,
        skill: str,
        override: str | None,
        first_prompt: str,
        scripted_replies: Sequence[str],
        session_id: str | None,
    ) -> AgentTurns:
        """What drives this case on this platform.

        A blank ``override`` counts as none, like an empty one: the preset drives the trial.

        :raises ValueError: when a multi-turn case is given an override, runs on a platform whose
            resume flags were never verified, or carries a session id that is not one token.
        """
        prompts = (first_prompt, *scripted_replies)
        override = override.strip() if override else None
        if len(prompts) == 1:
            return cls(override or preset_agent_command(platform, model, skill), None, prompts)
        if override:
            raise ValueError(
                "a multi-turn case runs on its platform's preset: one --agent-command cannot be "
                "both the template that opens a session and the one that resumes it"
            )
        if session_id is None or not _SESSION_ID.match(session_id):
            raise ValueError(
                f"a multi-turn trial's session id must be one opaque token (a uuid), not "
                f"{session_id!r}"
            )
        first = preset_first_turn_command(platform, model, skill)
        resumed = preset_resumed_turn_command(platform, model, skill)
        if first is None or resumed is None:
            raise ValueError(
                f"{platform} cannot drive a multi-turn case: its own multi-turn flags have never "
                "been verified in the container the trials run in"
            )
        return cls(
            first.replace(SESSION_PLACEHOLDER, session_id),
            resumed.replace(SESSION_PLACEHOLDER, session_id),
            prompts,
        )

    @property
    def turn_count(self) -> int:
        return len(self.prompts)

    def prompt_for_turn(self, turn: int) -> str:
        """What the agent is handed on ``turn``, 1-based."""
        return self.prompts[self._index(turn)]

    def command_for_turn(self, turn: int) -> str:
        """The template ``turn`` runs, session id already substituted."""
        if self._index(turn) == 0:
            return self.first_turn_command
        assert self.resumed_turn_command is not None, "checked at construction"
        return self.resumed_turn_command

    def _index(self, turn: int) -> int:
        if not 1 <= turn <= len(self.prompts):
            raise ValueError(f"turn {turn} is outside a conversation of {len(self.prompts)}")
        return turn - 1
