# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A read-only snapshot of a consumer project: everything the installer's decisions depend on, read
once and never read again.

INTENT: makes the planners pure functions. Every "does this file exist", "is this directory ours",
"where do traces land" question is answered here, so a plan can be computed, printed as a diff,
reviewed, and only then applied — with no chance of the answer changing between the diff and the
write.

Built two ways: :func:`~narrativetrace_tooling.init.project_state_reader.read_project_state` walks a
real directory; a test builds one directly with keyword arguments, which is why every planner case
is a unit test with no disk at all.

**@llmNote** Contents are kept byte for byte — line endings, byte-order mark, missing final newline
and all. The planners' edits are expressed against exactly these bytes.
"""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from enum import Enum, unique
from pathlib import Path
from types import MappingProxyType
from typing import Final

from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.platforms import table as platform_table

DEFAULT_OUTPUT_DIRECTORY: Final = "narrative-traces"
"""Where rendered traces land when a project says nothing else — the runtime's own default."""

PAGE: Final = "SKILL.md"
"""The page's file name inside a skill directory — the same in every flavour."""


@unique
class Presence(Enum):
    """What sits at a skill's path in the consumer project."""

    OURS = "ours"
    """A directory whose ``SKILL.md`` carries our provenance line — an install of ours."""

    FOREIGN = "foreign"
    """A directory somebody else owns: no page, or a page without our provenance line."""

    NOT_A_DIRECTORY = "not-a-directory"
    """Something that is not a directory at all sits at the path a skill needs."""

    LINKED_DIRECTORY = "linked-directory"
    """The skill's directory is a symbolic link; what a registry leaves at the vendor path."""

    LINKED_PAGE = "linked-page"
    """The directory is real, and its ``SKILL.md`` is a symbolic link."""


_LINKED: Final = frozenset({Presence.LINKED_DIRECTORY, Presence.LINKED_PAGE})
"""The two presences the installer must never write through."""


def _require_skill_identity(flavour: object, name: object, presence: object) -> None:
    """A skill is named, and found under one flavour as one kind of presence."""
    if not isinstance(flavour, SkillFlavour) or not isinstance(presence, Presence):
        raise TypeError("an installed skill needs a flavour and a presence")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("an installed skill's name must not be blank")


def _require_skill_text(*values: object) -> None:
    """Absence is the empty string throughout — a coordinate, a page body, a link target."""
    if not all(isinstance(value, str) for value in values):
        raise TypeError('use "" for an unknown coordinate, body or link, never None')


@dataclass(frozen=True, slots=True)
class InstalledSkill:
    """One skill directory found in a consumer project, and what the installer may do with it.

    INTENT: the planner's decision for a skill is a function of this value alone — is the directory
    ours (overwrite, no flag), somebody else's (refuse unless forced), a symbolic link (replace the
    link, or refuse — never write through it), or not a directory at all (refuse, always).

    :param flavour: which install root it was found under
    :param name: the directory name, which is the skill name
    :param presence: what was found there
    :param coordinate: the carrier a previous install stamped it with, ``""`` unless
        :attr:`Presence.OURS`
    :param body: the current ``SKILL.md`` text, ``""`` when there is none; for a link, the page it
        reaches INSIDE the project, and ``""`` when it reaches none
    :param link: what the symbolic link points at, exactly as the filesystem reports it — ``""``
        unless the presence is one of the two linked ones
    """

    flavour: SkillFlavour
    name: str
    presence: Presence
    coordinate: str = ""
    body: str = ""
    link: str = ""

    def __post_init__(self) -> None:
        _require_skill_identity(self.flavour, self.name, self.presence)
        _require_skill_text(self.coordinate, self.body, self.link)
        if self.presence is Presence.OURS and not self.coordinate.strip():
            raise ValueError("an installed skill of ours carries its coordinate")
        if (self.presence in _LINKED) is not bool(self.link.strip()):
            raise ValueError(
                "a linked presence names what the link points at, and only a linked one does"
            )

    @property
    def directory(self) -> Path:
        """The project-relative directory, e.g. ``.agents/skills/narrativetrace-doctor``."""
        return Path(self.flavour.install_root, self.name)

    @property
    def page(self) -> Path:
        """The project-relative page, e.g. ``.agents/skills/narrativetrace-doctor/SKILL.md``."""
        return self.directory / PAGE

    @property
    def is_linked(self) -> bool:
        """Whether this presence is one the installer must never write or delete THROUGH.

        The one place that knows which presences are linked, so a planner never has to list them and
        a presence added later cannot be forgotten at one of two sites.
        """
        return self.presence in _LINKED

    @property
    def linked_at(self) -> Path:
        """Where the symbolic link itself sits: the skill's directory, or its page.

        :raises ValueError: when nothing here is a link — a caller reading a field that has no
            meaning, rather than a project in a strange state
        """
        if not self.is_linked:
            raise ValueError(f"nothing links to {self.directory.as_posix()}")
        return self.page if self.presence is Presence.LINKED_PAGE else self.directory


@dataclass(frozen=True, slots=True)
class ProjectState:
    """Everything the installer reads about a project, read once.

    :param agents_md: the project's ``AGENTS.md``, byte for byte, or ``None`` when it has none
    :param claude_md: the project's ``CLAUDE.md``, byte for byte, or ``None`` when it has none
    :param claude_directory: whether the vendor directory exists — one half of vendor detection
    :param installed_skills: every skill directory found under either install root, in read order
    :param linked_install_roots: what a flavour's install root points at when the ROOT itself is a
        symbolic link — nothing may be written into that flavour at all, because every page of it,
        present or not, would land wherever the link goes
    :param marked_rule_files: vendor rule files that ALREADY carry our markers, by project-relative
        path. The installer never creates one of these; it keeps an existing block up to date.
    :param detected_platforms: the ids of the platform-table rows whose marker the project carries
        (``.cursor/``, ``replit.md``, …), read by exact path — a near miss such as ``.cursorx/``
        proves nothing
    :param pointer_files: an existing platform pointer file, byte for byte, by project-relative
        path; a path behind a symbolic link is never here
    :param pointers_behind_links: the pointer paths that run through a symbolic link, at the file or
        at a directory above it — nothing is read or written through one
    :param output_directory: where this project's rendered traces land, detected or
        :data:`DEFAULT_OUTPUT_DIRECTORY`
    :param uv_project: whether commands should be spelled ``uv run narrativetrace …``
    """

    agents_md: str | None = None
    claude_md: str | None = None
    claude_directory: bool = False
    installed_skills: tuple[InstalledSkill, ...] = ()
    linked_install_roots: Mapping[SkillFlavour, str] = field(default_factory=dict)
    marked_rule_files: Mapping[str, str] = field(default_factory=dict)
    detected_platforms: AbstractSet[str] = frozenset()
    pointer_files: Mapping[str, str] = field(default_factory=dict)
    pointers_behind_links: AbstractSet[str] = frozenset()
    output_directory: str = DEFAULT_OUTPUT_DIRECTORY
    uv_project: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "installed_skills", tuple(self.installed_skills))
        object.__setattr__(
            self, "linked_install_roots", MappingProxyType(dict(self.linked_install_roots))
        )
        object.__setattr__(
            self, "marked_rule_files", MappingProxyType(dict(self.marked_rule_files))
        )
        _freeze_platform_facts(self)
        if not isinstance(self.output_directory, str) or not self.output_directory.strip():
            raise ValueError("a project state names where traces land, even if only by default")
        assert _invariant(self), "a project state must describe one path once"

    def installed_skill(self, flavour: SkillFlavour, name: str) -> InstalledSkill | None:
        """The skill directory at one flavour's path, or ``None`` when nothing is there."""
        return next(
            (
                skill
                for skill in self.installed_skills
                if skill.flavour is flavour and skill.name == name
            ),
            None,
        )

    def linked_install_root(self, flavour: SkillFlavour) -> str | None:
        """What this flavour's install root points at when the root is a link, else ``None``."""
        return self.linked_install_roots.get(flavour)


def _freeze_platform_facts(state: ProjectState) -> None:
    """Immutable copies of the platform facts, refusing what no row could have produced."""
    unknown = sorted(set(state.detected_platforms) - {r.id for r in platform_table.ROWS})
    if unknown:
        raise ValueError(f"detected platforms must be rows of the platform table, got {unknown}")
    if not all(isinstance(text, str) for text in state.pointer_files.values()):
        raise TypeError("a pointer file's text is a string; absence is a missing key")
    both = sorted(set(state.pointer_files) & set(state.pointers_behind_links))
    if both:
        raise ValueError(f"{both} is read and behind a link at once — nothing is read through one")
    object.__setattr__(state, "detected_platforms", frozenset(state.detected_platforms))
    object.__setattr__(state, "pointer_files", MappingProxyType(dict(state.pointer_files)))
    object.__setattr__(state, "pointers_behind_links", frozenset(state.pointers_behind_links))


def _invariant(state: ProjectState) -> bool:
    """Returns whether a snapshot describes each path once, and describes nothing behind a link.

    Nothing is listed under a flavour whose whole install root is a link: what was found there was
    found THROUGH it, so naming it would invite the one write the refusal exists to prevent.

    Constructor guards make this true for every live instance; tests re-check it around each case.
    """
    described = [(skill.flavour, skill.name) for skill in state.installed_skills]
    return (
        len(set(described)) == len(described)
        and not any(skill.flavour in state.linked_install_roots for skill in state.installed_skills)
        and bool(state.output_directory.strip())
    )
