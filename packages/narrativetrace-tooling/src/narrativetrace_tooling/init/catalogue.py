# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A carrier's index: which runtime shipped it, which skills it carries, and where each rendered
flavour lives inside it.

INTENT: one place knows the shape of ``catalogue.json``. Every field is mandatory and every type is
checked at read time, so a malformed carrier is refused before any plan exists — with a message
naming the entry — rather than half-installed.

**@llmNote** The catalogue carries NO version, by design; do not add one. The stamp is the carrying
distribution's own coordinate, which :mod:`narrativetrace_tooling.init.carrier` derives separately,
so a checked-in catalogue can never drift from the artifact that ships it.

**@llmNote** Paths in a catalogue are carrier-relative and always use ``/``: they name entries
inside a distribution's payload, not paths on a particular filesystem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum, unique
from typing import Any, Final


@unique
class SkillFlavour(Enum):
    """The two rendered forms of the same skill a carrier ships, and where each one is installed.

    INTENT: a skill's text differs between the open-standard layout and the vendor layout by two
    frontmatter fields, so the carrier ships both rather than making an installer synthesise one
    from the other — rendering belongs in the catalogue, not in the installer.

    **@llmNote** :attr:`AGENTS` is written into every project. :attr:`CLAUDE` is written only where
    a project is detected as that vendor's, or where the caller asked for it explicitly; the planner
    owns that decision, not this enum.

    **@llmNote** The member VALUE is the catalogue field that carries this flavour's path
    (``"agents"``, ``"claude"``), and :attr:`install_root` is the project-relative directory it is
    written to. Declaration order is install order, and the loops over it depend on that.
    """

    AGENTS = "agents"
    """The open-standard flavour, installed under ``.agents/skills/``."""

    CLAUDE = "claude"
    """The vendor flavour, installed under ``.claude/skills/``."""

    @property
    def install_root(self) -> str:
        """The project-relative directory this flavour's skill directories live in."""
        return _INSTALL_ROOTS[self]


_INSTALL_ROOTS: Final[dict[SkillFlavour, str]] = {
    SkillFlavour.AGENTS: ".agents/skills",
    SkillFlavour.CLAUDE: ".claude/skills",
}


@dataclass(frozen=True, slots=True)
class SkillEntry:
    """One skill as a carrier's ``catalogue.json`` lists it.

    INTENT: the installer's unit of work. Everything a planner needs about a skill is here, so a
    plan can be computed without opening the carrier a second time.

    :param name: the skill's directory name in the consumer project, unique within a catalogue
    :param description: the one-paragraph trigger description, copied into the managed block as-is
    :param agents_path: carrier-relative path of the open-standard flavour's rendered page
    :param claude_path: carrier-relative path of the vendor flavour's rendered page
    """

    name: str
    description: str
    agents_path: str
    claude_path: str

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        _require_text(self.description, "description")
        _require_text(self.agents_path, "agents path")
        _require_text(self.claude_path, "claude path")

    def path_for(self, flavour: SkillFlavour) -> str:
        """The carrier-relative path of one flavour's rendered page.

        :raises ValueError: when no flavour is given
        """
        if flavour is None:
            raise ValueError("a flavour must be given to pick a skill's path")
        return self.agents_path if flavour is SkillFlavour.AGENTS else self.claude_path


@dataclass(frozen=True, slots=True)
class SkillCatalogue:
    """A whole ``catalogue.json``, validated once so every later stage can treat it as a fact.

    :param runtime: the runtime slug the carrier was rendered for, ``"python"`` here
    :param skills: every skill in catalogue order, each name appearing exactly once
    """

    runtime: str
    skills: tuple[SkillEntry, ...]

    def __post_init__(self) -> None:
        if not self.runtime or not self.runtime.strip():
            raise ValueError("a catalogue's runtime must not be blank")
        if not self.skills:
            raise ValueError("a catalogue must list at least one skill")
        names = [skill.name for skill in self.skills]
        if len(set(names)) != len(names):
            raise ValueError(f"a catalogue names a skill twice: {sorted(names)}")
        assert _invariant(self), "a catalogue must name each skill once"

    def skill(self, name: str) -> SkillEntry | None:
        """The entry with this name, or ``None`` — the lookup an installer does per target
        directory."""
        return next((skill for skill in self.skills if skill.name == name), None)


def _invariant(catalogue: SkillCatalogue) -> bool:
    """Returns whether a catalogue is structurally consistent.

    Constructor guards make this true for every live instance; tests re-check the same rules at
    fixture setup and teardown to catch a mutation that bypassed construction.
    """
    names = [skill.name for skill in catalogue.skills]
    return bool(catalogue.runtime.strip()) and bool(names) and len(set(names)) == len(names)


def read_catalogue(json_text: str) -> SkillCatalogue:
    """Reads a carrier's ``catalogue.json``.

    :param json_text: the whole document
    :raises ValueError: when the document is malformed, a field is missing or wrongly typed, or a
        skill name repeats. The message names the entry, because it reaches a person as one line of
        a refusal with no stack trace under it.
    """
    root = _as_object(_parse(json_text), "catalogue")
    runtime = _string(root, "runtime", "catalogue")
    skills = tuple(_entry(_as_object(element, "skill")) for element in _array(root, "skills"))
    catalogue = SkillCatalogue(runtime, skills)
    assert _invariant(catalogue), "a catalogue read from text holds the same rules as a built one"
    return catalogue


def _parse(json_text: str) -> object:
    """:func:`json.loads`, with the family's own message. Python's own reads "Expecting value:
    line 1 column 12 (char 11)"; every other runtime's carrier refusal says "malformed JSON at
    offset N", and this string is quoted into a refusal a person reads."""
    if json_text is None:
        raise ValueError("no JSON text to read")
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"malformed JSON at offset {error.pos}: {error.msg}") from error


def _entry(skill: dict[str, Any]) -> SkillEntry:
    name = _string(skill, "name", "skill")
    return SkillEntry(
        name,
        _string(skill, "description", name),
        _string(skill, "agents", name),
        _string(skill, "claude", name),
    )


def _as_object(value: object, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"catalogue: {what} must be a JSON object")
    return value


def _array(root: dict[str, Any], key: str) -> list[Any]:
    value = root.get(key)
    if not isinstance(value, list):
        raise ValueError(f'catalogue: "{key}" must be a JSON array')
    return value


def _string(owner: dict[str, Any], key: str, what: str) -> str:
    value = owner.get(key)
    if not isinstance(value, str):
        raise ValueError(f'catalogue: {what} has no "{key}" string field')
    return value


def _require_text(value: str, what: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"a catalogue skill's {what} must not be blank")
