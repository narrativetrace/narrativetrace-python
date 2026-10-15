# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The sporadic-lanes quota guard: "A weekly allowance per platform, in a ledger the runner
reads ... The runner refuses a platform whose allowance is spent and says so; there is no override
flag — the owner edits the ledger." Reads/writes ``ledger/quota.md`` (plan tier + weekly allowance
table, plus a spend log the runner appends to).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from platform_presets import Platform, cli_tool, is_sporadic_platform


@dataclass(frozen=True, slots=True)
class QuotaAllowance:
    platform: str
    plan_tier: str
    weekly_allowance: int


@dataclass(frozen=True, slots=True)
class QuotaSpendRow:
    date: str
    platform: str
    skill: str
    case_name: str
    week: str


@dataclass(frozen=True, slots=True)
class QuotaLedger:
    allowances: tuple[QuotaAllowance, ...]
    spend: tuple[QuotaSpendRow, ...]


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    allowed: bool
    reason: str | None = None


def iso_week(moment: date) -> str:
    """ISO 8601 week, e.g. ``"2026-W37"`` (Monday-start, week 1 contains the year's first
    Thursday) — ``date.isocalendar()`` implements exactly this rule."""
    iso_year, iso_week_number, _ = moment.isocalendar()
    return f"{iso_year}-W{iso_week_number:02d}"


_ROW_RE = re.compile(r"^\|(.+)\|$")


def _pipe_rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        match = _ROW_RE.match(stripped)
        if not match:
            continue
        cells = [cell.strip() for cell in match.group(1).split("|")]
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue  # the header separator row
        rows.append(cells)
    return rows[1:]  # drop the header row itself


def _section_body(content: str, heading: str) -> str:
    start = content.find(heading)
    if start == -1:
        return ""
    rest = content[start + len(heading) :]
    next_heading = re.search(r"\n## ", rest)
    return rest if next_heading is None else rest[: next_heading.start()]


def parse_quota_markdown(content: str) -> QuotaLedger:
    allowances = tuple(
        QuotaAllowance(platform=row[0], plan_tier=row[1], weekly_allowance=int(row[2] or 0))
        for row in _pipe_rows(_section_body(content, "## Allowance"))
    )
    spend = tuple(
        QuotaSpendRow(date=row[0], platform=row[1], skill=row[2], case_name=row[3], week=row[4])
        for row in _pipe_rows(_section_body(content, "## Spend log"))
    )
    return QuotaLedger(allowances=allowances, spend=spend)


def spend_count_this_week(ledger: QuotaLedger, platform: str, week: str) -> int:
    return sum(1 for row in ledger.spend if row.platform == platform and row.week == week)


def check_quota(ledger: QuotaLedger, platform: str, now: date | None = None) -> QuotaDecision:
    """No override flag by design: a spent allowance is fixed by editing ``ledger/quota.md``."""
    moment = now if now is not None else date.today()
    allowance = next((row for row in ledger.allowances if row.platform == platform), None)
    if allowance is None:
        return QuotaDecision(
            allowed=False, reason=f'ledger/quota.md carries no allowance row for "{platform}"'
        )
    week = iso_week(moment)
    spent = spend_count_this_week(ledger, platform, week)
    if spent >= allowance.weekly_allowance:
        return QuotaDecision(
            allowed=False,
            reason=(
                f"{platform}'s weekly allowance ({allowance.weekly_allowance}) is spent for "
                f"{week} ({spent} run(s) already) -- no override; the owner edits ledger/quota.md"
            ),
        )
    return QuotaDecision(allowed=True)


def skip_reason(platform: Platform, ledger: QuotaLedger) -> str | None:
    """The one line a lane prints INSTEAD of running when its weekly allowance is zero, or ``None``
    when the lane should go on to the precondition and quota checks.

    **@llmNote** A zero allowance row is the owner's own "the CLI is not installed or signed in yet"
    (the ledger convention for a lane whose CLI is not there yet, Cursor's today), so the lane skips
    and the run exits green — it never fails a build over a tool nobody has installed. A MISSING
    row, a spent allowance and a red tier are not that state: they stay refusals
    (:func:`check_quota`).
    """
    if not is_sporadic_platform(platform):
        return None
    not_installed = any(
        row.platform == platform and row.weekly_allowance == 0 for row in ledger.allowances
    )
    if not not_installed:
        return None
    return (
        f"SKIP: the {platform} lane did not run — its `{cli_tool(platform)}` CLI is not installed"
        " or signed in (weekly allowance 0 in ledger/quota.md); the owner raises the allowance"
        " once it is"
    )


def _ends_without_newline(path: Path) -> bool:
    """Whether a hand-edited ledger stops mid-line, where a new row would be glued onto the last."""
    content = path.read_bytes()
    return bool(content) and not content.endswith(b"\n")


def append_spend_row(quota_path: Path, row: QuotaSpendRow) -> None:
    """Appends one spend row to ``quota_path``'s "## Spend log" pipe table."""
    line = f"| {row.date} | {row.platform} | {row.skill} | {row.case_name} | {row.week} |\n"
    needs_newline = _ends_without_newline(quota_path)
    with quota_path.open("a", encoding="utf-8") as handle:
        handle.write(("\n" if needs_newline else "") + line)


__all__ = [
    "QuotaAllowance",
    "QuotaDecision",
    "QuotaLedger",
    "QuotaSpendRow",
    "append_spend_row",
    "check_quota",
    "iso_week",
    "parse_quota_markdown",
    "skip_reason",
    "spend_count_this_week",
]
