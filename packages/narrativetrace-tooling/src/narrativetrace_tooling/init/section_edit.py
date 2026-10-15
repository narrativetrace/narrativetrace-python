# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one decision for any file that may carry the managed section, shared by every planner that
writes one: ``AGENTS.md``, the vendor rule files and a platform's memory file (``replit.md``).

INTENT: a file's existing-content policy lives in one place. A file that is absent is created with
the ``narrativetrace:created`` note, one that carries exactly one section has just that section
replaced, and one that carries none is appended to only when the caller has permission — and never
when it ends inside an unfinished fence, carries a broken marker, or carries two sections.

**@sideEffects** None. Pure functions from text to an
:class:`~narrativetrace_tooling.init.action.Action`.
"""

from __future__ import annotations

from pathlib import Path

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.action import Action, AppendBlock, CreateFile, Refuse, ReplaceBlock
from narrativetrace_tooling.init.options import InitOptions


def managed_home(path: Path, existing: str | None, block: str, options: InitOptions) -> Action:
    """A markdown file that is ours to create and may carry the section: made with the created note
    when absent, kept current when it has a section, appended to only on ``--write-existing``."""
    if existing is None:
        return CreateFile(path, marked_block.CREATED_NOTE + "\n" + block)
    return block_action(path, existing, block, may_write_existing=options.write_existing)


def block_action(path: Path, text: str, block: str, *, may_write_existing: bool) -> Action:
    """The same decision for any file that may carry the section: our home and the rule files."""
    scan = marked_block.scan(text)
    if scan.problems:
        return Refuse(path, f"{path}: {'; '.join(scan.problems)}")
    if len(scan.regions) > 1:
        at = ", ".join(f"line {region.start_line}" for region in scan.regions)
        return Refuse(
            path, f"{path} carries two or more NarrativeTrace sections ({at}) — leave exactly one"
        )
    matched = marked_block.with_eol(block, marked_block.eol_of(text))
    if len(scan.regions) == 1:
        return ReplaceBlock(path, text, marked_block.replace(text, scan.regions[0], matched))
    if not may_write_existing:
        return Refuse(
            path,
            f"{path} exists and carries no NarrativeTrace section — re-run with --write-existing"
            " to append one",
        )
    if marked_block.ends_inside_fence(text):
        return Refuse(path, unfinished_fence(path))
    return AppendBlock(path, text, matched)


def unfinished_fence(path: Path) -> str:
    """A file that ends inside an unfinished fenced code block cannot be appended to: whatever is
    added lands inside that fence, invisible to this installer's own markers and to every Markdown
    reader, so the next run would add it again."""
    return (
        f"{path} ends inside an unfinished fenced code block — close the fence, and anything"
        " appended after it will be read as text rather than as code"
    )
