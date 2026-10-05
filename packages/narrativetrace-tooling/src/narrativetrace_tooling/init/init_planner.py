# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Decides what an install would do — and nothing else.

INTENT: a pure function of ``(ProjectState, Carrier, InitOptions)``. Every existing-file policy
lives here and only here, which is why each row of it is a unit test with no filesystem at all, and
why a ``--dry-run`` diff is exactly what a real run would write.

**@llmNote** An action whose result equals what is already there is dropped, so planning a project
that is already current yields an EMPTY plan. That is what makes a re-run idempotent, and it is the
property the round-trip tests lean on.

**@llmNote** A refusal never stops the plan: the rest of the actions are still planned, and the run
exits 1. One bad file must not cost a project its other nine.

**@sideEffects** None. Nothing here reads a file or writes one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from narrativetrace_tooling.init import marked_block, provenance
from narrativetrace_tooling.init.action import (
    Action,
    AppendBlock,
    AppendLine,
    CreateFile,
    FileEdit,
    Refuse,
    ReplaceBlock,
)
from narrativetrace_tooling.init.agents_md_block import render_agents_md_block
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.catalogue import SkillEntry, SkillFlavour
from narrativetrace_tooling.init.options import InitOptions, Vendor
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import PAGE, Presence, ProjectState

AGENTS_MD: Final = Path("AGENTS.md")
"""The managed home, the one file the section is ever written into."""

CLAUDE_MD: Final = Path("CLAUDE.md")
"""The vendor context file, which gets an import line and never a copy of the section."""

IMPORT_LINE: Final = "@AGENTS.md"
"""The line that points the vendor's context file at the managed home."""


def plan_init(state: ProjectState, carrier: Carrier, options: InitOptions) -> InitPlan:
    """The plan an install with these options would apply to this project."""
    if state is None or carrier is None or options is None:
        raise TypeError("planning needs a project state, a carrier and options")
    actions: list[Action] = []
    if options.scope.includes_skills:
        actions += _skill_actions(state, carrier, options)
    if options.scope.includes_agents_md:
        actions += _agents_md_actions(state, carrier, options)
    return InitPlan(carrier.coordinate, options.dry_run, _without_no_ops(actions))


# --- skills ---------------------------------------------------------------------------------------


def _skill_actions(state: ProjectState, carrier: Carrier, options: InitOptions) -> list[Action]:
    return [
        _skill_action(state, carrier, options, skill, flavour)
        for skill in carrier.skills
        for flavour in _flavours(state, options)
    ]


def _flavours(state: ProjectState, options: InitOptions) -> tuple[SkillFlavour, ...]:
    """Which flavours this project gets: the open standard always, the vendor one where the project
    looks like that vendor's — or wherever the caller overrode the detection."""
    detected = state.claude_directory or state.claude_md is not None
    vendor = {Vendor.ON: True, Vendor.OFF: False, Vendor.AUTO: detected}[options.vendor_claude]
    return (SkillFlavour.AGENTS, SkillFlavour.CLAUDE) if vendor else (SkillFlavour.AGENTS,)


def _skill_action(
    state: ProjectState,
    carrier: Carrier,
    options: InitOptions,
    skill: SkillEntry,
    flavour: SkillFlavour,
) -> Action:
    directory = Path(flavour.install_root, skill.name)
    page = directory / PAGE
    content = provenance.stamp(carrier.body(skill, flavour), carrier.coordinate)
    installed = state.installed_skill(flavour, skill.name)
    if installed is None:
        return CreateFile(page, content)
    if installed.presence is Presence.NOT_A_DIRECTORY:
        return Refuse(
            directory, f"{directory} is not a directory — move it aside and run the install again"
        )
    if installed.presence is Presence.FOREIGN and not options.force:
        return Refuse(
            directory,
            f"{directory} was not installed by narrativetrace — re-run with --force to overwrite"
            " this skill, or move the directory aside",
        )
    return _write(page, installed.body, content)


def _write(page: Path, current: str, content: str) -> Action:
    """A write is a create when nothing is there and a replacement when something is."""
    return CreateFile(page, content) if not current else ReplaceBlock(page, current, content)


# --- the managed section --------------------------------------------------------------------------


def _agents_md_actions(state: ProjectState, carrier: Carrier, options: InitOptions) -> list[Action]:
    block = render_agents_md_block(carrier, state)
    actions = [_agents_md_action(state, block, options)]
    claude_md = _claude_md_action(state, options)
    if claude_md is not None:
        actions.append(claude_md)
    actions += [
        _block_action(Path(path), text, block, may_write_existing=False)
        for path, text in state.marked_rule_files.items()
    ]
    return actions


def _agents_md_action(state: ProjectState, block: str, options: InitOptions) -> Action:
    if state.agents_md is None:
        return CreateFile(AGENTS_MD, marked_block.CREATED_NOTE + "\n" + block)
    return _block_action(
        AGENTS_MD, state.agents_md, block, may_write_existing=options.write_existing
    )


def _block_action(path: Path, text: str, block: str, *, may_write_existing: bool) -> Action:
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
        return Refuse(path, _unfinished_fence(path))
    return AppendBlock(path, text, matched)


def _claude_md_action(state: ProjectState, options: InitOptions) -> Action | None:
    """The import line: never created, added to an existing vendor context file that lacks it."""
    text = state.claude_md
    if text is None or marked_block.line_is_ignoring_trailing_space(text, IMPORT_LINE) is not None:
        return None
    if not options.write_existing:
        return Refuse(
            CLAUDE_MD,
            f"{CLAUDE_MD} exists and does not import {AGENTS_MD} — re-run with --write-existing"
            " to add the one-line import",
        )
    if marked_block.ends_inside_fence(text):
        return Refuse(CLAUDE_MD, _unfinished_fence(CLAUDE_MD))
    return AppendLine(CLAUDE_MD, text, IMPORT_LINE)


def _unfinished_fence(path: Path) -> str:
    """A file that ends inside an unfinished fenced code block cannot be appended to: whatever is
    added lands inside that fence, invisible to this installer's own markers and to every Markdown
    reader, so the next run would add it again."""
    return (
        f"{path} ends inside an unfinished fenced code block — close the fence, and anything"
        " appended after it will be read as text rather than as code"
    )


def _without_no_ops(actions: list[Action]) -> tuple[Action, ...]:
    """Drops every action that would write what is already there."""
    return tuple(action for action in actions if _changes_something(action))


def _changes_something(action: Action) -> bool:
    return not isinstance(action, FileEdit) or action.before != action.after
