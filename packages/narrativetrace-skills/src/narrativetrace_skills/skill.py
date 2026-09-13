# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The typed catalogue schema (mirrors the TypeScript runtime's ``skill.ts``). A :class:`Skill` is
the source of truth :mod:`narrativetrace_skills.render` turns into per-platform artifacts
(``SKILL.md``, the ``AGENTS.md`` snippet) — never hand-write those; regenerate them
(``python scripts/skills_render.py --fix``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SkillClass = Literal["mechanical", "guided", "judgmental"]
"""Drives which case kinds the eval harness expects."""

COMMAND_VOCABULARY: tuple[str, ...] = ("uv", "git")
"""The closed per-port command vocabulary: a ``commands`` step's first token must be one of
these, or Tier A fails naming the offending step. This port's toolchain is ``uv`` (and, through
it, the project venv's own ``python``/``pytest``/``narrativetrace``) plus ``git`` — never a global
binary, never a package manager this port does not use."""


@dataclass(frozen=True, slots=True)
class CommandStep:
    """A step that runs one or more shell commands, replayed verbatim against the fixture
    (Tier A2)."""

    commands: tuple[str, ...]
    kind: Literal["commands"] = "commands"


@dataclass(frozen=True, slots=True)
class SnippetStep:
    """A step that shows real, current source rather than a hand-typed example — rendered
    through the same ``<!-- snippet: path -->`` marker convention ``scripts/snippet_check.py``
    already enforces for docs. ``path`` is repo-root-relative."""

    path: str
    language: str
    mask: str | None = None
    kind: Literal["snippet"] = "snippet"


StepBody = CommandStep | SnippetStep


@dataclass(frozen=True, slots=True)
class FailureNote:
    """Symptom -> cause -> fix, verbose enough to act on."""

    symptom: str
    cause: str
    fix: str


@dataclass(frozen=True, slots=True)
class SkillStep:
    title: str
    body: StepBody
    verify: str | None = None
    """A ``commands``-vocabulary string proving the step succeeded. ``None`` only for a
    judgmental step."""
    failure: tuple[FailureNote, ...] = ()
    flag: str | None = None
    """e.g. ``"unstudied — eval cell pending"``."""


@dataclass(frozen=True, slots=True)
class ReasonedRule:
    """A ``never``/``always`` rule WITH its reason — a naked prohibition does not survive an edge
    case; a reasoned one does."""

    rule: str
    reason: str


@dataclass(frozen=True, slots=True)
class Skill:
    canonical_name: str
    """Globally self-identifying, flat-namespace-safe, e.g. ``narrativetrace-doctor``."""
    claude_segment: str
    """The Claude plugin's shortened segment, e.g. ``doctor`` -> ``/narrativetrace:doctor``."""
    skill_class: SkillClass
    description: str
    """<=1024 chars, third person, WHAT + WHEN with mined trigger phrasings."""
    fixture: str
    """Repo-root-relative fixture the skill is exercised against."""
    steps: tuple[SkillStep, ...]
    allowed_tools: tuple[str, ...]
    """Emitted into ``allowed-tools`` — the command vocabulary this skill uses."""
    when_to_use: str | None = None
    always: tuple[ReasonedRule, ...] = ()
    never: tuple[ReasonedRule, ...] = ()


_DESCRIPTION_BUDGET = 1024


def command_strings(skill: Skill) -> tuple[str, ...]:
    """Every string a lint should check ``skill``'s ``commands`` steps against the closed
    vocabulary."""
    return tuple(
        command
        for step in skill.steps
        if isinstance(step.body, CommandStep)
        for command in step.body.commands
    )


def first_token(command: str) -> str:
    """The first whitespace-separated token of a shell command — what the vocabulary check
    looks at."""
    parts = command.strip().split()
    return parts[0] if parts else ""


def vocabulary_violations(skill: Skill) -> tuple[str, ...]:
    """Every ``commands`` string violating the closed command vocabulary, in ``skill: command``
    form."""
    return tuple(
        f"{skill.canonical_name}: {command}"
        for command in command_strings(skill)
        if first_token(command) not in COMMAND_VOCABULARY
    )


def description_fits_budget(skill: Skill) -> bool:
    """``description`` fits the per-skill budget (the catalogue-wide budget is a separate
    index-level lint)."""
    return len(skill.description) <= _DESCRIPTION_BUDGET


def steps_without_verify(skill: Skill) -> tuple[str, ...]:
    """The replayability rule: every step must carry a ``verify`` UNLESS it is explicitly
    judgmental (no ``verify``, and the reason is documented in ``flag`` or the step's own body —
    the schema cannot enforce prose, only that the step is not silently missing one)."""
    return tuple(step.title for step in skill.steps if step.verify is None)
