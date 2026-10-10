# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The framework table, rendered for readers (Phase 6 D2): the framework table at the top of
`llms-full.md`'s "Integrations" and the covered-frameworks line in `llms.txt`.

INTENT: the doctor, the docs and the skill all answer "which frameworks, which package, which
lines" -- so all three read `narrativetrace_tooling.frameworks.table`, and none is typed. Each
rendered block sits between `<!-- <name>:begin -->`/`<!-- <name>:end -->` markers; `poe
snippet-sync` rewrites them (this module's `sync`, run before the snippet blocks are resynced) and
`poe snippet-check` fails while they disagree (`check`). The wiring snippets inside the table carry
the same `<!-- snippet: -->` markers as the doctor's own resource, so the snippet gate holds the
page to the fixtures as well. Mirrors Java's `FrameworkTableDocs`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.version_literals import read_version

from narrativetrace_tooling.frameworks.table import (
    ROWS,
    FrameworkRow,
    NoCheck,
    NoIntegration,
    Snippet,
)
from narrativetrace_tooling.frameworks.wiring_snippets import entries

LLMS_FULL = "documentation/llms-full.md"
LLMS_TXT = "documentation/llms.txt"

_TABLE_BLOCK = "framework-table"
_COVERED_BLOCK = "covered-frameworks"
_FENCE = "```"


def framework_table_section(version: str) -> str:
    """The table and every source-wired row's snippet, for `llms-full.md`."""
    lines = [
        "### Framework table — what the doctor checks\n\n",
        "Rendered from the doctor's own framework table. For every row it can observe, `uv run "
        "narrativetrace doctor` runs the named check: the framework is detected but its "
        "integration is not added, or it is added but its wiring was never applied — and the "
        "failing fix prints the lines below. A framework with no integration shipped is reported, "
        "never guessed at.\n\n",
        "| Framework | Detected by | Add | Wiring | Doctor check |\n",
        "|---|---|---|---|---|\n",
    ]
    lines.extend(_table_row(row, version) for row in ROWS)
    lines.extend(_snippet_section(row) for row in ROWS if isinstance(row.wiring, Snippet))
    return "".join(lines)


def covered_frameworks_line() -> str:
    """One line naming every row, in table order, for `llms.txt`."""
    covered = "; ".join(f"{row.name} ({_coverage(row)})" for row in ROWS)
    return f"Covered frameworks (each row of the doctor's framework table): {covered}."


def splice(document: str, name: str, content: str) -> str:
    """`document` with everything between the `name` markers replaced by `content`.

    :raises ValueError: when the document lacks either marker, or has them out of order
    """
    begin = f"<!-- {name}:begin -->\n"
    end = f"<!-- {name}:end -->"
    start = document.find(begin)
    stop = document.find(end)
    if start < 0 or stop < start:
        raise ValueError(f"the document has no {name}:begin / {name}:end marker pair")
    return document[: start + len(begin)] + content + document[stop:]


def check(repo_root: Path) -> list[str]:
    """Each document whose rendered blocks differ from what the table renders now."""
    return [
        f"{relative}: the framework table has drifted from the doctor's — run 'poe snippet-sync'"
        for relative, rendered in _rendered(repo_root).items()
        if (repo_root / relative).read_text(encoding="utf-8") != rendered
    ]


def sync(repo_root: Path) -> list[str]:
    """Rewrites each drifted document in place; returns the ones it rewrote."""
    rewritten = []
    for relative, rendered in _rendered(repo_root).items():
        path = repo_root / relative
        if path.read_text(encoding="utf-8") != rendered:
            path.write_text(rendered, encoding="utf-8")
            rewritten.append(relative)
    return rewritten


def _rendered(repo_root: Path) -> dict[str, str]:
    version = read_version(repo_root)
    full = (repo_root / LLMS_FULL).read_text(encoding="utf-8")
    txt = (repo_root / LLMS_TXT).read_text(encoding="utf-8")
    return {
        LLMS_FULL: splice(full, _TABLE_BLOCK, framework_table_section(version)),
        LLMS_TXT: splice(txt, _COVERED_BLOCK, covered_frameworks_line() + "\n"),
    }


def _table_row(row: FrameworkRow, version: str) -> str:
    add = "—" if row.module is None else f"`{row.module.add_instruction(version)}`"
    cells = (row.name, row.marker.description, add, row.wiring.description, _check_cell(row))
    return "| " + " | ".join(cells) + " |\n"


def _check_cell(row: FrameworkRow) -> str:
    if isinstance(row.check, NoCheck):
        return f"none — {row.check.reason}"
    suffix = " (reports it)" if isinstance(row.wiring, NoIntegration) else ""
    return f"`{row.check.id}`{suffix}"


def _coverage(row: FrameworkRow) -> str:
    if isinstance(row.wiring, NoIntegration):
        return "no integration shipped"
    if isinstance(row.check, NoCheck):
        return row.check.reason.split(" — ", 1)[0]
    return f"`{row.check.id}`"


def _snippet_section(row: FrameworkRow) -> str:
    entry = entries()[row.id]
    region = "" if entry.region is None else f" region={entry.region}"
    return (
        f"\n#### {row.name} — wiring\n\n<!-- snippet: {entry.fixture}{region} -->\n"
        f"{_FENCE}python\n{entry.body}{_FENCE}\n<!-- /snippet -->\n"
    )
