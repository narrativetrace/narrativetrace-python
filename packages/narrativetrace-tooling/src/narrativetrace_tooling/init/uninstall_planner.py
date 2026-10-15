# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Decides what an uninstall would remove — exactly what the installer wrote, and nothing beside it.

INTENT: the other half of the promise that makes an install safe to try. A skill directory is
removed only when its page carries our provenance line, whatever carrier stamped it; the managed
section is removed from its markers out; the import line is removed only when it is still character
for character the line the installer added.

**@llmNote** A file is DELETED only when the installer created it (the ``narrativetrace:created``
note on its first line) and nothing but our own content is left in it. A file the installer merely
appended to is always kept, even if removing our section empties it.

**@sideEffects** None. Pure, like the install planner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.action import (
    Action,
    DeleteDirectory,
    DeleteFile,
    Refuse,
    ReplaceBlock,
)
from narrativetrace_tooling.init.cursor_rule import FRONTMATTER
from narrativetrace_tooling.init.init_planner import AGENTS_MD, CLAUDE_MD, IMPORT_LINE
from narrativetrace_tooling.init.options import InitOptions
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import Presence, ProjectState
from narrativetrace_tooling.platforms.table import ROWS, Rule

UNKNOWN_CARRIER: Final = "narrativetrace-skills==unknown"
"""What an uninstall reports as its carrier when the project carries no stamp at all."""


def plan_uninstall(state: ProjectState, options: InitOptions) -> InitPlan:
    """The plan an uninstall with these options would apply to this project."""
    if state is None or options is None:
        raise TypeError("planning an uninstall needs a project state and options")
    actions: list[Action] = []
    if options.scope.includes_skills:
        actions += _skill_actions(state)
    if options.scope.includes_agents_md:
        actions += _section_actions(state)
    return InitPlan(_installed_coordinate(state), options.dry_run, tuple(actions))


def _skill_actions(state: ProjectState) -> list[Action]:
    """The page first, then the directory it was the only reason for."""
    actions: list[Action] = []
    for skill in state.installed_skills:
        if skill.presence is Presence.OURS:
            actions.append(DeleteFile(skill.page, skill.body))
            actions.append(DeleteDirectory(skill.directory))
    return actions


def _section_actions(state: ProjectState) -> list[Action]:
    actions: list[Action] = []
    if state.agents_md is not None:
        actions += _remove_section(AGENTS_MD, state.agents_md, may_delete=True)
    actions += _remove_import_line(state)
    for path, text in state.marked_rule_files.items():
        # A rule file is never deleted: the installer never created one.
        actions += _remove_section(Path(path), text, may_delete=False)
    return actions + _pointer_actions(state)


def _pointer_actions(state: ProjectState) -> list[Action]:
    """Every platform pointer the table names, whether or not the platform's marker is still there:
    what the installer wrote is removed even after the project stopped looking like that platform.
    A pointer behind a link was never written by us and is not in the snapshot."""
    actions: list[Action] = []
    for row in ROWS:
        text = state.pointer_files.get(row.pointer.path)
        if text is None:
            continue
        path = Path(row.pointer.path)
        if isinstance(row.pointer, Rule):
            actions += _remove_rule(path, text)
        else:
            actions += _remove_section(path, text, may_delete=True)
    return actions


def _remove_rule(path: Path, text: str) -> list[Action]:
    """A rule file is deleted when nothing but its frontmatter is left once our section is gone —
    the installer made it — and otherwise loses only the section, so a rule the user added below
    ours survives."""
    scan = marked_block.scan(text)
    if scan.problems or len(scan.regions) > 1:
        return [_refuse_by_hand(path)]
    if not scan.regions:
        return []
    remainder = marked_block.remove(text, scan.regions[0])
    bare = marked_block.with_eol(marked_block.without_byte_order_mark(remainder), "\n")
    if bare == FRONTMATTER:
        return [DeleteFile(path, text)]
    return [ReplaceBlock(path, text, remainder)]


def _refuse_by_hand(path: Path) -> Refuse:
    return Refuse(
        path, f"{path} does not carry exactly one NarrativeTrace section — remove it by hand"
    )


def _remove_section(path: Path, text: str, *, may_delete: bool) -> list[Action]:
    scan = marked_block.scan(text)
    if scan.problems or len(scan.regions) > 1:
        return [_refuse_by_hand(path)]
    if not scan.regions:
        return []
    without_section = marked_block.remove(text, scan.regions[0])
    created = marked_block.line_is(without_section, marked_block.CREATED_NOTE)
    remainder = (
        marked_block.remove(without_section, created) if created is not None else without_section
    )
    if (
        may_delete
        and created is not None
        and not marked_block.without_byte_order_mark(remainder).strip()
    ):
        return [DeleteFile(path, text)]
    return [ReplaceBlock(path, text, remainder)]


def _remove_import_line(state: ProjectState) -> list[Action]:
    """Removed only when it is still character for character the line the installer added."""
    text = state.claude_md
    if text is None:
        return []
    line = marked_block.line_is(text, IMPORT_LINE)
    if line is None:
        return []
    return [ReplaceBlock(CLAUDE_MD, text, marked_block.remove(text, line))]


def _installed_coordinate(state: ProjectState) -> str:
    """The coordinate this project was installed from: the stamp on the managed section, else the
    one on the first skill of ours, else an honest ``unknown``."""
    from_section = _section_coordinate(state)
    if from_section:
        return from_section
    return next(
        (skill.coordinate for skill in state.installed_skills if skill.presence is Presence.OURS),
        UNKNOWN_CARRIER,
    )


def _section_coordinate(state: ProjectState) -> str:
    if state.agents_md is None:
        return ""
    scan = marked_block.scan(state.agents_md)
    return scan.regions[0].coordinate if scan.has_exactly_one_region() else ""
