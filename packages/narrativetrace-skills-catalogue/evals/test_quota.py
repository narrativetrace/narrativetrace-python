# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from datetime import date
from pathlib import Path

from quota import (
    QuotaAllowance,
    QuotaLedger,
    QuotaSpendRow,
    append_spend_row,
    check_quota,
    iso_week,
    parse_quota_markdown,
    skip_reason,
    spend_count_this_week,
)

_SAMPLE_MARKDOWN = """# Sporadic eval quota

## Allowance

| platform | plan tier | weekly allowance |
|---|---|---|
| codex | basic | 4 |
| antigravity | not installed | 0 |

## Spend log

| date | platform | skill | case | week |
|---|---|---|---|---|
| 2026-09-10T00:00:00 | codex | narrativetrace-doctor | happy-path | 2026-W37 |
"""


class TestIsoWeek:
    def test_a_known_monday(self) -> None:
        assert iso_week(date(2026, 9, 7)) == "2026-W37"

    def test_a_year_boundary_belongs_to_the_previous_iso_year(self) -> None:
        # 2027-01-01 is a Friday, in ISO week 53 of 2026.
        assert iso_week(date(2027, 1, 1)) == "2026-W53"


class TestParseQuotaMarkdown:
    def test_parses_allowances(self) -> None:
        ledger = parse_quota_markdown(_SAMPLE_MARKDOWN)
        assert ledger.allowances == (
            QuotaAllowance(platform="codex", plan_tier="basic", weekly_allowance=4),
            QuotaAllowance(platform="antigravity", plan_tier="not installed", weekly_allowance=0),
        )

    def test_parses_spend_rows(self) -> None:
        ledger = parse_quota_markdown(_SAMPLE_MARKDOWN)
        assert ledger.spend == (
            QuotaSpendRow(
                date="2026-09-10T00:00:00",
                platform="codex",
                skill="narrativetrace-doctor",
                case_name="happy-path",
                week="2026-W37",
            ),
        )

    def test_empty_document_has_no_allowances_or_spend(self) -> None:
        ledger = parse_quota_markdown("# empty\n")
        assert ledger.allowances == ()
        assert ledger.spend == ()


class TestSpendCountThisWeek:
    def test_counts_matching_rows(self) -> None:
        ledger = parse_quota_markdown(_SAMPLE_MARKDOWN)
        assert spend_count_this_week(ledger, "codex", "2026-W37") == 1

    def test_zero_for_an_unspent_week(self) -> None:
        ledger = parse_quota_markdown(_SAMPLE_MARKDOWN)
        assert spend_count_this_week(ledger, "codex", "2026-W01") == 0


class TestCheckQuota:
    def test_allows_when_under_the_weekly_allowance(self) -> None:
        ledger = parse_quota_markdown(_SAMPLE_MARKDOWN)
        decision = check_quota(ledger, "codex", now=date(2026, 9, 7))
        assert decision.allowed is True

    def test_refuses_a_platform_with_no_allowance_row(self) -> None:
        ledger = QuotaLedger(allowances=(), spend=())
        decision = check_quota(ledger, "claude")
        assert decision.allowed is False
        assert decision.reason is not None and "claude" in decision.reason

    def test_refuses_once_the_weekly_allowance_is_spent(self) -> None:
        allowance = QuotaAllowance(platform="codex", plan_tier="basic", weekly_allowance=1)
        spend = (
            QuotaSpendRow(date="x", platform="codex", skill="s", case_name="c", week="2026-W37"),
        )
        ledger = QuotaLedger(allowances=(allowance,), spend=spend)
        decision = check_quota(ledger, "codex", now=date(2026, 9, 7))
        assert decision.allowed is False
        assert decision.reason is not None and "no override" in decision.reason

    def test_antigravity_at_zero_allowance_always_refuses(self) -> None:
        ledger = parse_quota_markdown(_SAMPLE_MARKDOWN)
        decision = check_quota(ledger, "antigravity", now=date(2026, 9, 7))
        assert decision.allowed is False


class TestAppendSpendRow:
    def test_appends_one_pipe_row(self, tmp_path: Path) -> None:
        quota_path = tmp_path / "quota.md"
        quota_path.write_text(
            "## Spend log\n\n| date | platform | skill | case | week |\n", encoding="utf-8"
        )
        append_spend_row(
            quota_path,
            QuotaSpendRow(
                date="2026-09-13", platform="codex", skill="s", case_name="c", week="2026-W37"
            ),
        )
        content = quota_path.read_text(encoding="utf-8")
        assert "| 2026-09-13 | codex | s | c | 2026-W37 |" in content

    def test_round_trips_through_parse(self, tmp_path: Path) -> None:
        quota_path = tmp_path / "quota.md"
        quota_path.write_text(_SAMPLE_MARKDOWN, encoding="utf-8")
        row = QuotaSpendRow(
            date="2026-09-13", platform="codex", skill="s", case_name="c", week="2026-W37"
        )
        append_spend_row(quota_path, row)
        ledger = parse_quota_markdown(quota_path.read_text(encoding="utf-8"))
        assert row in ledger.spend


class TestSkipReason:
    """A zero allowance row is the owner's own "the CLI is not installed or signed in yet", so the
    lane skips and the run stays green. A MISSING row, a spent allowance and a non-sporadic lane
    are not that state."""

    def test_a_zero_allowance_skips_with_one_line_naming_the_tool(self) -> None:
        ledger = parse_quota_markdown(_SAMPLE_MARKDOWN)

        assert skip_reason("antigravity", ledger) == (
            "SKIP: the antigravity lane did not run — its `agy` CLI is not installed or signed in"
            " (weekly allowance 0 in ledger/quota.md); the owner raises the allowance once it is"
        )

    def test_cursors_skip_line_names_the_agent_executable_not_the_lane(self) -> None:
        allowance = QuotaAllowance(platform="cursor", plan_tier="not installed", weekly_allowance=0)

        line = skip_reason("cursor", QuotaLedger(allowances=(allowance,), spend=()))

        assert line is not None
        assert line.startswith("SKIP: the cursor lane did not run — its `agent` CLI")

    def test_the_line_is_one_line(self) -> None:
        ledger = parse_quota_markdown(_SAMPLE_MARKDOWN)

        assert "\n" not in (skip_reason("antigravity", ledger) or "\n")

    def test_a_lane_with_allowance_left_does_not_skip(self) -> None:
        assert skip_reason("codex", parse_quota_markdown(_SAMPLE_MARKDOWN)) is None

    def test_a_missing_row_is_a_refusal_and_not_a_skip(self) -> None:
        assert skip_reason("cursor", QuotaLedger(allowances=(), spend=())) is None

    def test_a_spent_allowance_is_a_refusal_and_not_a_skip(self) -> None:
        allowance = QuotaAllowance(platform="codex", plan_tier="basic", weekly_allowance=1)
        spend = (QuotaSpendRow("2026-09-07", "codex", "s", "c", "2026-W37"),)

        assert skip_reason("codex", QuotaLedger(allowances=(allowance,), spend=spend)) is None

    def test_the_claude_lane_is_exempt_even_with_a_zero_row(self) -> None:
        allowance = QuotaAllowance(platform="claude", plan_tier="n/a", weekly_allowance=0)

        assert skip_reason("claude", QuotaLedger(allowances=(allowance,), spend=())) is None
