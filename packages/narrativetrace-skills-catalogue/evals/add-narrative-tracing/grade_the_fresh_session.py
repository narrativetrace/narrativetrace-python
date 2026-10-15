# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Grades the fresh-session cases: the session AFTER the install must see the skills it left.

Shared by two cases. ``fresh-session-sees-the-skills`` lets the harness run this checkout's own
installer first (``"registry": "narrativetrace-init"``) and gives the agent ONE fresh turn;
``fresh-session-after-the-prompt`` keeps the agent's own install in the loop (the published prompt,
a scripted approval of the diff, then a fresh turn, ``"freshTurns": [3]``). Either way two things
gate, both read from the transcript's LAST turn:

  1. the turn's ``system/init`` event lists every skill the catalogue ships (the objective half:
     the skills are LOADED, whatever the agent then does with them);
  2. the agent reached for the doctor -- the ``narrativetrace-doctor`` skill by name through the
     Skill tool, or the doctor command itself -- rather than answering from memory.

Why both: item 166 (2026-10-10) was an install that went green and a next session that listed no
skill. Gate 1 is that finding, stated as a measurement. Gate 2 is why the skills matter at all: a
session that lists them and never uses them on a question written to trigger one is the skill
failing to fire (a model reading), which the trigger samples measure on a phrasing set and this
case measures once, on a real project the agent just installed into.

Run from the scaffolded project copy, with ``$NARRATIVETRACE_TRANSCRIPT`` pointing at this trial's
evidence, which lives outside this project. The transcript reader is the feedback cases' own -- one
record format, one reader.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Final, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "narrativetrace-feedback"))

import transcript

EXPECTED_SKILLS: Final = (
    "add-narrative-tracing",
    "add-narrativetrace-clarity",
    "narrativetrace-doctor",
    "narrativetrace-feedback",
    "narrativetrace-verify",
    "narrativetrace-debug",
    "narrativetrace-explain",
)
DOCTOR_SKILL: Final = "narrativetrace-doctor"
DOCTOR_COMMAND: Final = re.compile(r"narrativetrace\s+doctor\b|narrativetrace\.doctor\b")


def verdict(turns: list[transcript.Turn]) -> str | None:
    """Why the fresh session fails, or ``None`` when it passes."""
    if not turns:
        return "the transcript records no turn at all"
    fresh = turns[-1]
    missing = [skill for skill in EXPECTED_SKILLS if skill not in fresh.available_skills]
    if missing:
        listed = ", ".join(fresh.available_skills) or "nothing"
        return (
            f"the fresh session's init event does not list these skills: {', '.join(missing)} "
            f"(it lists: {listed})"
        )
    if not _reached_for_the_doctor(fresh):
        return (
            f"the fresh session listed the skills but reached for neither the {DOCTOR_SKILL} skill "
            "nor the doctor command on a question written to trigger it"
        )
    return None


def _reached_for_the_doctor(turn: transcript.Turn) -> bool:
    return any(_used_the_skill(call) or DOCTOR_COMMAND.search(call.text) for call in turn.calls)


def _used_the_skill(call: transcript.ToolCall) -> bool:
    return call.name == "Skill" and call.input.get("skill") == DOCTOR_SKILL


def main() -> None:
    path = os.environ.get("NARRATIVETRACE_TRANSCRIPT")
    if not path or not os.path.isfile(path):
        _fail("no transcript at $NARRATIVETRACE_TRANSCRIPT -- the runner records every trial")
    turns = transcript.read(Path(path))
    failure = verdict(turns)
    if failure:
        _fail(failure)
    how = "skill" if any(_used_the_skill(call) for call in turns[-1].calls) else "command"
    print(
        "grade_the_fresh_session: the fresh session lists every skill and reached for the "
        f"doctor ({how})"
    )


def _fail(message: str) -> NoReturn:
    print(f"grade_the_fresh_session: {message}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
