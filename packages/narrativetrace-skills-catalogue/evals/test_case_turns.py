# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The scripted user replies a case declares. Every way of being wrong THROWS rather than degrading
to a shorter conversation: a case whose second turn silently did not happen passes its approval
grader for the worst reason -- nothing was filed because nothing was asked. Ports Java's
``CaseTurnsTest``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from case_turns import scripted_replies_for


def _case(tmp_path: Path, manifest: object) -> Path:
    (tmp_path / "case.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_a_case_with_no_manifest_is_one_turn(tmp_path: Path) -> None:
    assert scripted_replies_for(tmp_path) == []


def test_a_case_declaring_no_turns_is_one_turn(tmp_path: Path) -> None:
    assert scripted_replies_for(_case(tmp_path, {"fixture": "f"})) == []


def test_reads_the_replies_in_turn_order_whatever_order_the_file_lists_them(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, {"turns": {"3": "and then this", "2": "yes, file it"}})

    assert scripted_replies_for(case) == ["yes, file it", "and then this"]


def test_turn_ten_comes_after_turn_nine_not_after_turn_one(tmp_path: Path) -> None:
    turns = {str(n): f"reply {n}" for n in range(2, 11)}

    assert scripted_replies_for(_case(tmp_path, {"turns": turns}))[-2:] == [
        "reply 9",
        "reply 10",
    ]


def test_a_reply_keeps_its_quotes_and_line_breaks(tmp_path: Path) -> None:
    case = _case(tmp_path, {"turns": {"2": 'no -- "do not"\nfile it'}})

    assert scripted_replies_for(case) == ['no -- "do not"\nfile it']


@pytest.mark.parametrize(
    ("turns", "message"),
    [
        ({}, r'declares "turns" and lists no reply in it\Z'),
        ([], r'declares "turns" as something other than an object\Z'),
        ("yes", r'declares "turns" as something other than an object\Z'),
        ({"two": "yes"}, r'declares a turn keyed "two", which is not a turn number\Z'),
        ({"1": "yes"}, r"declares a reply at turn 1 -- turn 1 is the case's own prompt\.md"),
        ({"0": "yes"}, r"declares a reply at turn 0 -- turn 1 is the case's own prompt\.md"),
        ({"-2": "yes"}, r'declares a turn keyed "-2", which is not a turn number\Z'),
        ({"2": "   "}, r"declares a blank reply at turn 2"),
        ({"2": 7}, r"declares a reply at turn 2 that is not text\Z"),
        ({"3": "yes"}, r"declares no reply for turn 2, so turn 3 could never be reached\Z"),
        (
            {"2": "a", "4": "b"},
            r"declares no reply for turn 3, so turn 4 could never be reached\Z",
        ),
    ],
)
def test_refuses_every_declaration_that_cannot_be_driven(
    tmp_path: Path, turns: object, message: str
) -> None:
    case = _case(tmp_path, {"turns": turns})

    with pytest.raises(
        ValueError, match=r"\A" + re.escape(str(case / "case.json")) + " " + message
    ):
        scripted_replies_for(case)


def test_refuses_two_spellings_of_one_turn(tmp_path: Path) -> None:
    """``"2"`` and ``"02"`` are the same turn; keeping either silently drops the other reply."""
    case = _case(tmp_path, {"turns": {"2": "yes", "02": "no"}})

    with pytest.raises(ValueError, match=r"declares turn 2 twice\Z"):
        scripted_replies_for(case)
