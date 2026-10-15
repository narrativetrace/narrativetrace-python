# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Decides which platform pointers an install writes (Phase 8, platform pointers).

INTENT: one pointer per DETECTED platform whose row has one. The marker decides, never a flag: a
project not on Cursor gets no ``.cursor/`` directory it did not have. A pointer is a rule file the
installer renders (``cursor_rule``) or a managed section in the platform's own memory file, adopted
when it is already ours, refused when it is somebody's, and never written through a link.

**@sideEffects** None. Pure, like the rest of the planners.
"""

from __future__ import annotations

from pathlib import Path

from narrativetrace_tooling.init import adoption, marked_block
from narrativetrace_tooling.init.action import Action, AdoptPage, CreateFile, Refuse, ReplaceBlock
from narrativetrace_tooling.init.agents_md_block import render_agents_md_block
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.cursor_rule import FRONTMATTER, render_cursor_rule
from narrativetrace_tooling.init.options import InitOptions
from narrativetrace_tooling.init.project_state import ProjectState
from narrativetrace_tooling.init.section_edit import managed_home
from narrativetrace_tooling.platforms.table import ROWS, ManagedSection, Pointer, Rule


def plan_pointers(state: ProjectState, carrier: Carrier, options: InitOptions) -> list[Action]:
    """One pointer per DETECTED platform whose row has one. The marker decides, never a flag: a
    project not on Cursor gets no ``.cursor/`` directory it did not have."""
    return [
        _pointer_action(row.pointer, state, carrier, options)
        for row in ROWS
        if row.id in state.detected_platforms and row.pointer.path
    ]


def _pointer_action(
    pointer: Pointer, state: ProjectState, carrier: Carrier, options: InitOptions
) -> Action:
    path = Path(pointer.path)
    if pointer.path in state.pointers_behind_links:
        return Refuse(
            path,
            f"{path} is behind a symbolic link — nothing is written through one; remove the link",
        )
    existing = state.pointer_files.get(pointer.path)
    if isinstance(pointer, Rule):
        return _rule_action(path, existing, pointer, carrier)
    assert isinstance(pointer, ManagedSection), "a pointer with a path is a rule or a section"
    return managed_home(path, existing, render_agents_md_block(carrier, state), options)


def _rule_action(path: Path, existing: str | None, rule: Rule, carrier: Carrier) -> Action:
    """The rule file: made when absent, kept current when ours, ADOPTED when it is the unstamped
    plugin copy byte for byte, and refused when it carries no section of ours at all."""
    wanted = render_cursor_rule(rule.text, carrier.coordinate)
    if existing is None:
        return CreateFile(path, wanted)
    if adoption.is_adoptable(existing, render_cursor_rule(rule.text, "")):
        return AdoptPage(path, existing, wanted)
    scan = marked_block.scan(existing)
    if not scan.has_exactly_one_region():
        return Refuse(
            path,
            f"{path} was not written by narrativetrace (it has no single NarrativeTrace section) —"
            " move it aside and run the install again",
        )
    section = marked_block.with_eol(wanted[len(FRONTMATTER) :], marked_block.eol_of(existing))
    return ReplaceBlock(path, existing, marked_block.replace(existing, scan.regions[0], section))
