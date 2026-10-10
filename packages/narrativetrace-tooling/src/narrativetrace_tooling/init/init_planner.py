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

from narrativetrace_tooling.init import adoption, marked_block, provenance
from narrativetrace_tooling.init.action import (
    Action,
    AdoptPage,
    AppendBlock,
    AppendLine,
    CreateFile,
    FileEdit,
    Refuse,
    ReplaceBlock,
    ReplaceLink,
)
from narrativetrace_tooling.init.agents_md_block import render_agents_md_block
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.catalogue import SkillEntry, SkillFlavour
from narrativetrace_tooling.init.options import InitOptions, Vendor
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import (
    PAGE,
    InstalledSkill,
    Presence,
    ProjectState,
)

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
    refusals, writable = _writable_flavours(state, options)
    return refusals + [
        _skill_action(state, carrier, options, skill, flavour)
        for skill in carrier.skills
        for flavour in writable
    ]


def _writable_flavours(
    state: ProjectState, options: InitOptions
) -> tuple[list[Action], list[SkillFlavour]]:
    """The flavours anything may be written into, and the refusals for the ones that are links.

    A flavour whose whole install root is a symbolic link is refused ONCE, here, rather than once
    per skill (rule 20): one link is one decision, and a refusal per skill would also put several
    actions on the one path a plan allows only one of.
    """
    refusals: list[Action] = []
    writable: list[SkillFlavour] = []
    for flavour in _flavours(state, options):
        target = state.linked_install_root(flavour)
        if target is None:
            writable.append(flavour)
        else:
            refusals.append(_refuse_linked_root(flavour, target))
    return refusals, writable


def _refuse_linked_root(flavour: SkillFlavour, target: str) -> Refuse:
    root = flavour.install_root
    return Refuse(
        Path(root),
        f"{root} is a symbolic link to {target} — every skill of this flavour would be written"
        " through it; remove the link, or run the install where it points",
    )


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
    rendered = carrier.body(skill, flavour)
    content = provenance.stamp(rendered, carrier.coordinate)
    installed = state.installed_skill(flavour, skill.name)
    if installed is None:
        return CreateFile(page, content)
    if installed.presence is Presence.OURS:
        return _write(page, installed.body, content)
    if installed.presence is Presence.FOREIGN:
        return _foreign(options, installed, rendered, content)
    if installed.is_linked:
        return _linked(carrier, skill, installed, content)
    # NOT_A_DIRECTORY, and the fall-through for any presence added later: the safe answer is the
    # refusal, never the write. A presence nobody has taught this planner about must cost a person
    # one message, not a file.
    return Refuse(
        directory, f"{directory} is not a directory — move it aside and run the install again"
    )


def _linked(carrier: Carrier, skill: SkillEntry, installed: InstalledSkill, content: str) -> Action:
    """A symbolic link where a skill's directory or page belongs.

    Writing through it would land in whatever it points at — after ``npx skills add``, the OTHER
    flavour's page — so the link itself is replaced whenever what it reaches is a page this install
    owns or would adopt, and refused otherwise. No flag appears here (rule 19): ``--force`` covers
    foreign CONTENT, and a link is structure.
    """
    at = installed.linked_at
    if not installed.body:
        return Refuse(
            at,
            f"{at} is a symbolic link to {installed.link}, and there is no page of narrativetrace's"
            " at the other end — remove the link and run the install again",
        )
    if not _is_ours_or_adoptable(carrier, skill, installed.body):
        return Refuse(
            at,
            f"{at} is a symbolic link to {installed.link}, a page narrativetrace did not install —"
            " remove the link and run the install again; --force covers content, never a link",
        )
    return ReplaceLink(at, installed.page, installed.link, content)


def _is_ours_or_adoptable(carrier: Carrier, skill: SkillEntry, body: str) -> bool:
    """Whether a page reached through a link is one this install would own anyway: already stamped,
    or identical to what this carrier renders for EITHER flavour.

    Either flavour, because the link a registry leaves at the vendor path points at the
    open-standard page.
    """
    if provenance.coordinate_in(body) is not None:
        return True
    return any(adoption.is_adoptable(body, carrier.body(skill, each)) for each in SkillFlavour)


def _foreign(
    options: InitOptions, installed: InstalledSkill, rendered: str, content: str
) -> Action:
    """A directory somebody else's tool wrote. A page equal to what this carrier renders is
    ADOPTED — it is our own page, installed by a registry rather than by us, so stamping it takes
    nothing from anybody. Anything else is a refusal until ``--force`` says otherwise.

    **@llmNote** The adoption test comes BEFORE the force check on purpose (rule 21: order, not a
    flag). A ``--force`` run over a registry tree must behave like the safe one, or a person
    following the refusal's own advice would overwrite the page the refusal was protecting.
    """
    if adoption.is_adoptable(installed.body, rendered):
        return AdoptPage(installed.page, installed.body, content)
    if not options.force:
        return Refuse(
            installed.directory,
            f"{installed.directory} was not installed by narrativetrace — re-run with --force to"
            " overwrite this skill, or move the directory aside",
        )
    return _write(installed.page, installed.body, content)


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
