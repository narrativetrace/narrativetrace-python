# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A2 oracle replay: mechanically executes a skill's own step data against its fixture, no
LLM. Green means the instructions are literally executable today — this is the harness's H1 (does
the skill still work), caught deterministically."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from narrativetrace_skills.skill import CommandStep, Skill, SkillStep

RunReplayCommand = Callable[[str, str], None]


@dataclass(frozen=True, slots=True)
class StepReplayResult:
    title: str
    ran: bool
    """``False`` when the step is pure narrative (no commands, no verify) — nothing to replay."""
    ok: bool
    error: str | None = None


def _commands_of(step: SkillStep) -> tuple[str, ...]:
    from_body = step.body.commands if isinstance(step.body, CommandStep) else ()
    ordered = (*from_body, step.verify) if step.verify else from_body
    # Deduplicated, order preserved (a dict's insertion order, keys deduplicated) -- a step whose
    # `commands` already equals its `verify` runs it once, not twice.
    return tuple(dict.fromkeys(ordered))


def run_replay_command(command: str, cwd: str) -> None:
    """Runs one shell command in ``cwd``, letting a nonzero exit or spawn failure propagate as a
    raised exception. ``shell=True`` is deliberate and safe here: every command replayed comes
    from this package's OWN typed catalogue (never user input), the same closed, reviewed set the
    Tier A vocabulary lint already constrains to `uv`/`git`."""
    subprocess.run(command, shell=True, cwd=cwd, capture_output=True, check=True)  # nosec B602 - command always comes from this package's own typed, reviewed catalogue


def _replay_step(step: SkillStep, cwd: str, run: RunReplayCommand) -> StepReplayResult:
    commands = _commands_of(step)
    if not commands:
        return StepReplayResult(title=step.title, ran=False, ok=True)
    try:
        for command in commands:
            run(command, cwd)
        return StepReplayResult(title=step.title, ran=True, ok=True)
    except Exception as error:  # reported as a result, not raised -- replay never crashes the run
        return StepReplayResult(title=step.title, ran=True, ok=False, error=str(error))


def replay_skill(
    skill: Skill, cwd: str, run: RunReplayCommand = run_replay_command
) -> tuple[StepReplayResult, ...]:
    """Replays every step of ``skill`` against ``cwd`` (the skill's fixture, checked out for
    real). ``run`` is injectable so a unit test can fake command execution without a real shell."""
    return tuple(_replay_step(step, cwd, run) for step in skill.steps)
