# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The platform table, rendered for readers (Phase 8, platform pointers): the table at the top of
``documentation/use-with-your-agent.md``.

INTENT: the page's one claim that changes with the vendors — how a stranger gets the skills on each
platform and what the agent finds — is a view of ``narrativetrace_tooling.platforms.table``, never
typed. The block sits between ``<!-- platform-table:begin -->``/``<!-- platform-table:end -->``;
``poe snippet-sync`` rewrites it (this module's :func:`sync`) and ``poe snippet-check`` fails while
the page disagrees (:func:`check`). The Verified column is the honesty: no test reaches the vendors,
so each row carries the date its facts were last checked. Mirrors Java's ``PlatformTableDocs``.

**@llmNote** A cell never carries a pipe or a newline: the translations of the page mirror the
table's shape, and a stray pipe would add a column to the English page only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.framework_table_docs import splice as splice_block

from narrativetrace_tooling.platforms.table import MANUAL, ROWS, PlatformRow

PAGE = "documentation/use-with-your-agent.md"
"""The page this table is rendered into, repository-relative."""

BLOCK = "platform-table"


def table() -> str:
    """The Markdown table: a header, a separator, and one line per platform in table order."""
    header = (
        "| Platform | How a stranger gets the skills | What the agent finds after `init` |"
        " Evidence | Verified |\n|---|---|---|---|---|\n"
    )
    return header + "".join(_line(row) for row in ROWS)


def splice(page: str) -> str:
    """The page with its table block re-rendered.

    :raises ValueError: when the page lacks the block's markers
    """
    return splice_block(page, BLOCK, table())


def check(repo_root: Path) -> list[str]:
    """The page when its table differs from what the platform table renders now."""
    path = repo_root / PAGE
    if path.read_text(encoding="utf-8") == splice(path.read_text(encoding="utf-8")):
        return []
    return [f"{PAGE}: the platform table has drifted from the installer's — run 'poe snippet-sync'"]


def sync(repo_root: Path) -> list[str]:
    """Rewrites the page in place when it drifted; returns it when it did."""
    path = repo_root / PAGE
    current = path.read_text(encoding="utf-8")
    rendered = splice(current)
    if rendered == current:
        return []
    path.write_text(rendered, encoding="utf-8")
    return [PAGE]


def _line(row: PlatformRow) -> str:
    cells = (row.name, row.install_path, row.agent_finds, _evidence(row), row.verified)
    return "| " + " | ".join(_cell(cell) for cell in cells) + " |\n"


def _evidence(row: PlatformRow) -> str:
    if row.evidence_lane == MANUAL:
        return "manual trial"
    return f"Tier B lane `{row.evidence_lane}`"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
