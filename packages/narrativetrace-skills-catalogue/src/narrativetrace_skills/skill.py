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
    condition: str | None = None
    """When present, rendered as a ``**when:**`` line under the heading: the step applies only
    then, and the line says what to do instead — prose a reader or agent branches on, never a
    list of frameworks (the page names none). Never blank."""
    done: str | None = None
    """When present, rendered as a ``**done when:**`` line after the body: what the reply or the
    project must show once the step is done, in prose. Kept apart from :attr:`verify`, which in
    this catalogue is always a runnable command — a judgmental step (write the intent, read the
    trace, report) has a done-condition and no command that could prove it. Never blank."""

    def __post_init__(self) -> None:
        if self.condition is not None and not self.condition.strip():
            raise ValueError("a SkillStep's condition must not be blank when present")
        if self.verify is not None and not self.verify.strip():
            raise ValueError("a SkillStep's verify must not be blank when present")
        if self.done is not None and not self.done.strip():
            raise ValueError("a SkillStep's done condition must not be blank when present")


@dataclass(frozen=True, slots=True)
class ReasonedRule:
    """A ``never``/``always`` rule WITH its reason — a naked prohibition does not survive an edge
    case; a reasoned one does."""

    rule: str
    reason: str


_LINE_BREAKS = frozenset("\n\r\u2028\u2029")
"""What ends a line for some reader of a rendered page — a heading carries none."""


@dataclass(frozen=True, slots=True)
class SkillSection:
    """A named block of reference text a skill renders after its steps — a table or a short list
    the steps point at, which is neither a step nor an always/never rule.

    INTENT: two skills that read traces share one "how to read a trace" text; a section is how
    that text is written once in the catalogue and rendered into both pages identically, instead
    of being copied into a step's prose where the copies drift.
    """

    heading: str
    """Rendered as a level-two heading: one line of text, never itself a heading marker."""
    markdown: str
    """Rendered as written."""

    def __post_init__(self) -> None:
        if not self.heading.strip():
            raise ValueError("a SkillSection's heading must not be blank")
        if any(c in self.heading for c in _LINE_BREAKS) or self.heading.startswith("#"):
            raise ValueError(
                f"a SkillSection's heading is one line of text, not markdown: {self.heading!r}"
            )
        if not self.markdown.strip():
            raise ValueError("a SkillSection's markdown must not be blank")


@dataclass(frozen=True, slots=True)
class Skill:
    canonical_name: str
    """Globally self-identifying, flat-namespace-safe, e.g. ``narrativetrace-doctor`` -- the
    single source for every rendered artifact's directory name and frontmatter ``name:``
    (ruling, skills design, 2026-09-04, reaffirmed 2026-09-13): a shortened segment is legitimate
    only inside a Claude plugin whose prefix already carries the brand, which nothing in this
    repo is -- a repo-level ``.claude/skills/`` directory is itself a flat namespace where a
    shortened name like ``doctor`` would collide with every other vendor's skill of that name."""
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
    sections: tuple[SkillSection, ...] = ()
    """Reference sections, rendered after the steps and before the always/never rules."""


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


def claude_tool_pattern(command: str) -> str:
    """The Claude Code ``allowed-tools`` spelling of one vocabulary command: a ``Bash(<command>
    *)`` permission rule. A bare command name (``"git"``) names no tool Claude Code recognises
    and pre-approves nothing -- ``allowed-tools`` lists TOOLS, and a permission rule is spelled
    ``Tool`` or ``Tool(specifier)``. The trailing ``" *"`` is load-bearing twice: a rule's
    wildcard sits after the subcommand, and it also matches the bare command on its own, which is
    what lets ``Bash(uv *)`` cover a plain ``uv``.

    The ONLY place this platform spelling is written -- the catalogue declares bare commands
    (:data:`Skill.allowed_tools`), :mod:`narrativetrace_skills.render.claude` is the one caller,
    and :func:`narrativetrace_skills.lints.allowed_tools_violations` is what keeps a hand-written
    pattern out of the catalogue itself."""
    return f"Bash({command} *)"


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
    judgmental — a ``done`` condition says in prose what the reply must show, which no command
    could prove. A step with neither is returned (its reason may still be documented in ``flag``
    or its body — the schema cannot enforce prose, only that the step is not silently missing
    one)."""
    return tuple(step.title for step in skill.steps if step.verify is None and step.done is None)
