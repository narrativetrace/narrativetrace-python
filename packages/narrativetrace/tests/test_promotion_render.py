# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/promotion_render.py`: the promotion matrix has one column per Tier B lane (Phase 8,
platform pointers, adds Cursor) and its committed file is a fresh render of the ledger."""

from __future__ import annotations

import pytest
from scripts.promotion_render import (
    _PROMOTION_PATH,
    _RUNS_PATH,
    LedgerRow,
    _expected_content,
    parse_runs_jsonl,
    render_promotion_markdown,
)


def _row(platform: str, result: str = "pass", case: str = "happy-path") -> LedgerRow:
    return LedgerRow("2026-10-10T00:00:00", "demo", case, platform, "auto", 1, result)


class TestTheColumns:
    def test_one_column_per_lane_cursor_last(self) -> None:
        lines = render_promotion_markdown(("demo",), ()).splitlines()

        assert "| Skill | Claude | Codex | Antigravity | Cursor |" in lines
        assert "|---|---|---|---|---|" in lines
        assert "| `demo` | not yet run | not yet run | not yet run | not yet run |" in lines

    def test_a_cursor_row_in_the_ledger_lands_in_the_cursor_column_only(self) -> None:
        text = render_promotion_markdown(("demo",), (_row("cursor", "fail"),))

        assert (
            "| `demo` | not yet run | not yet run | not yet run | red (auto, 2026-10-10) |" in text
        )

    def test_a_cursor_pass_does_not_turn_another_lanes_cell(self) -> None:
        text = render_promotion_markdown(("demo",), (_row("cursor"),))

        assert "| `demo` | not yet run | not yet run | not yet run |" in text

    def test_the_committed_matrix_is_a_fresh_render(self) -> None:
        assert _PROMOTION_PATH.read_text(encoding="utf-8") == _expected_content()


class TestTheLedgerRecordsModelIds:
    """B-99: an alias in ``model`` splits the matrix's groups and made a fresh render differ."""

    def test_the_committed_ledger_parses_with_every_row_a_full_model_id(self) -> None:
        content = _RUNS_PATH.read_text(encoding="utf-8")

        assert len(parse_runs_jsonl(content)) > 0

    def test_a_row_carrying_an_alias_is_refused_naming_the_row(self) -> None:
        line = (
            '{"date": "2026-10-18T00:00:00", "skill": "s", "case": "c", "platform": "p",'
            ' "model": "haiku", "trial": 1, "result": "pass"}'
        )

        with pytest.raises(
            ValueError, match=r"\Aledger row 1: model 'haiku' is not a full model id\Z"
        ):
            parse_runs_jsonl(line)
