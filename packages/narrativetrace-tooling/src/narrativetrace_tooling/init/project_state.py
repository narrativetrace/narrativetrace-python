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
from dataclasses import dataclass, field
from enum import Enum, unique
from pathlib import Path
from types import MappingProxyType
from typing import Final

from narrativetrace_tooling.init.catalogue import SkillFlavour

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


@dataclass(frozen=True, slots=True)
class InstalledSkill:
    """One skill directory found in a consumer project, and what the installer may do with it.

    INTENT: the planner's decision for a skill is a function of this value alone — is the directory
    ours (overwrite, no flag), somebody else's (refuse unless forced), or not a directory at all
    (refuse, always).

    :param flavour: which install root it was found under
    :param name: the directory name, which is the skill name
    :param presence: what was found there
    :param coordinate: the carrier a previous install stamped it with, ``""`` unless
        :attr:`Presence.OURS`
    :param body: the current ``SKILL.md`` text, ``""`` when there is none
    """

    flavour: SkillFlavour
    name: str
    presence: Presence
    coordinate: str = ""
    body: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.flavour, SkillFlavour) or not isinstance(self.presence, Presence):
            raise TypeError("an installed skill needs a flavour and a presence")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("an installed skill's name must not be blank")
        if not isinstance(self.coordinate, str) or not isinstance(self.body, str):
            raise TypeError('use "" for an unknown coordinate or body, never None')
        if self.presence is Presence.OURS and not self.coordinate.strip():
            raise ValueError("an installed skill of ours carries its coordinate")

    @property
    def directory(self) -> Path:
        """The project-relative directory, e.g. ``.agents/skills/narrativetrace-doctor``."""
        return Path(self.flavour.install_root, self.name)

    @property
    def page(self) -> Path:
        """The project-relative page, e.g. ``.agents/skills/narrativetrace-doctor/SKILL.md``."""
        return self.directory / PAGE


@dataclass(frozen=True, slots=True)
class ProjectState:
    """Everything the installer reads about a project, read once.

    :param agents_md: the project's ``AGENTS.md``, byte for byte, or ``None`` when it has none
    :param claude_md: the project's ``CLAUDE.md``, byte for byte, or ``None`` when it has none
    :param claude_directory: whether the vendor directory exists — one half of vendor detection
    :param installed_skills: every skill directory found under either install root, in read order
    :param marked_rule_files: vendor rule files that ALREADY carry our markers, by project-relative
        path. The installer never creates one of these; it keeps an existing block up to date.
    :param output_directory: where this project's rendered traces land, detected or
        :data:`DEFAULT_OUTPUT_DIRECTORY`
    :param uv_project: whether commands should be spelled ``uv run narrativetrace …``
    """

    agents_md: str | None = None
    claude_md: str | None = None
    claude_directory: bool = False
    installed_skills: tuple[InstalledSkill, ...] = ()
    marked_rule_files: Mapping[str, str] = field(default_factory=dict)
    output_directory: str = DEFAULT_OUTPUT_DIRECTORY
    uv_project: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "installed_skills", tuple(self.installed_skills))
        object.__setattr__(
            self, "marked_rule_files", MappingProxyType(dict(self.marked_rule_files))
        )
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


def _invariant(state: ProjectState) -> bool:
    """Returns whether a snapshot describes each path once.

    Constructor guards make this true for every live instance; tests re-check it around each case.
    """
    described = [(skill.flavour, skill.name) for skill in state.installed_skills]
    return len(set(described)) == len(described) and bool(state.output_directory.strip())
