# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial cases for the eval quota ledger: the ISO-week boundary at a year's edge, an
allowance cell left empty, and a ledger whose last line has no newline, which ``append_spend_row``
must not glue a new row onto.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from quota import (
    QuotaSpendRow,
    append_spend_row,
    check_quota,
    iso_week,
    parse_quota_markdown,
    spend_count_this_week,
)

_HEADER = (
    "# Sporadic eval quota\n\n"
    "## Allowance\n\n"
    "| platform | plan tier | weekly allowance |\n"
    "|---|---|---|\n"
    "| codex | basic | 4 |\n"
    "| antigravity | | |\n\n"
    "## Spend log\n\n"
    "| date | platform | skill | case | week |\n"
    "|---|---|---|---|---|\n"
)


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    path = tmp_path / "quota.md"
    path.write_text(_HEADER, encoding="utf-8")
    return path


class TestIsoWeekAtTheYearEdge:
    @pytest.mark.parametrize(
        ("day", "week"),
        [
            (date(2027, 1, 1), "2026-W53"),
            (date(2025, 12, 29), "2026-W01"),
            (date(2026, 12, 31), "2026-W53"),
        ],
    )
    def test_a_week_belongs_to_the_iso_year_its_thursday_falls_in(
        self, day: date, week: str
    ) -> None:
        assert iso_week(day) == week


class TestAnEmptyAllowanceCell:
    def test_an_empty_allowance_is_zero_so_the_platform_is_refused_not_unlimited(
        self, ledger_path: Path
    ) -> None:
        ledger = parse_quota_markdown(ledger_path.read_text(encoding="utf-8"))

        decision = check_quota(ledger, "antigravity", now=date(2026, 10, 7))

        assert decision.allowed is False
        assert decision.reason is not None
        assert decision.reason.startswith(
            "antigravity's weekly allowance (0) is spent for 2026-W41"
        )


class TestAppendingKeepsTheTableIntact:
    def test_appending_to_a_ledger_whose_last_line_has_no_newline_keeps_both_rows(
        self, tmp_path: Path
    ) -> None:
        """A hand-edited ledger may end without a newline. The append must start its row on a
        line of its own, or the new row is glued onto the last one and both are lost."""
        path = tmp_path / "quota.md"
        path.write_text(_HEADER + "| 2026-10-01 | codex | s | c | 2026-W40 |", encoding="utf-8")

        append_spend_row(path, QuotaSpendRow("2026-10-07", "codex", "s", "c", "2026-W41"))

        ledger = parse_quota_markdown(path.read_text(encoding="utf-8"))
        assert spend_count_this_week(ledger, "codex", "2026-W40") == 1
        assert spend_count_this_week(ledger, "codex", "2026-W41") == 1
