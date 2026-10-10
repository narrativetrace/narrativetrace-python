# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""INTENT: the scripted user replies that drive a Tier B case past its first turn, read from the
case's own ``case.json``. Ports Java's ``CaseTurns``.

A case without them is one turn -- every case written before the feedback ones. A case WITH them is
a conversation the runner drives, and that is the only way to measure something that must happen
in a LATER turn than the one that asked: an approval.

The declaration is keyed BY TURN NUMBER (``"turns": {"2": "yes, file it"}``) rather than being a
bare array, because the turn a reply is given at is the subject of these cases and an array makes
it implicit in its own ordering. Turn 1 is always the case's own ``prompt.md``.

This is the ONE home of a scripted reply: the graders read the same field through
:func:`scripted_replies_for` rather than taking the words as an argument (Java duplicated them
between ``verify.sh`` and ``case.json`` and they drifted within the hour).

**@llmNote** Every way of being wrong RAISES rather than degrading to a shorter conversation. A
case whose second turn silently did not happen passes its approval grader for the wrong reason --
nothing was filed because nothing was asked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

_FIELD: Final = "turns"
_TURN_NUMBER: Final = re.compile(r"\A[0-9]+\Z")


def scripted_replies_for(case_dir: Path) -> list[str]:
    """The replies ``case_dir`` declares, in turn order; empty for a single-turn case.

    :raises ValueError: naming ``case.json`` and the reason, for any declaration that cannot be
        driven turn by turn from turn 2.
    """
    manifest_path = case_dir / "case.json"
    if not manifest_path.is_file():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"{manifest_path} is not a JSON object")
    if _FIELD not in manifest:
        return []
    declared = manifest[_FIELD]
    if not isinstance(declared, dict):
        raise ValueError(f'{manifest_path} declares "turns" as something other than an object')
    if not declared:
        raise ValueError(f'{manifest_path} declares "turns" and lists no reply in it')
    by_turn: dict[int, str] = {}
    for key, reply in declared.items():
        turn = _turn_number(manifest_path, key)
        if turn in by_turn:
            raise ValueError(f"{manifest_path} declares turn {turn} twice")
        by_turn[turn] = _reply(manifest_path, turn, reply)
    _require_contiguous_from_the_second_turn(manifest_path, by_turn)
    replies = [by_turn[turn] for turn in sorted(by_turn)]
    assert len(replies) == len(declared), "every declared reply is driven"
    return replies


def _turn_number(manifest_path: Path, key: str) -> int:
    """A key is a turn number, and the first turn a reply can be given at is the second."""
    if not _TURN_NUMBER.match(key.strip()):
        raise ValueError(
            f'{manifest_path} declares a turn keyed "{key}", which is not a turn number'
        )
    turn = int(key)
    if turn < 2:
        raise ValueError(
            f"{manifest_path} declares a reply at turn {turn} -- turn 1 is the case's own "
            "prompt.md, so the first reply is turn 2"
        )
    return turn


def _reply(manifest_path: Path, turn: int, reply: object) -> str:
    if not isinstance(reply, str):
        raise ValueError(f"{manifest_path} declares a reply at turn {turn} that is not text")
    if not reply.strip():
        raise ValueError(
            f"{manifest_path} declares a blank reply at turn {turn} -- a turn with nothing to say "
            "cannot be driven"
        )
    return reply


def _require_contiguous_from_the_second_turn(manifest_path: Path, by_turn: dict[int, str]) -> None:
    """Turns 2..n, nothing missing. Closing a gap quietly would hand a later turn's reply to an
    earlier turn -- for an approval case, a question answered versus a question never asked."""
    for expected, declared in enumerate(sorted(by_turn), start=2):
        if declared != expected:
            raise ValueError(
                f"{manifest_path} declares no reply for turn {expected}, so turn {declared} "
                "could never be reached"
            )
