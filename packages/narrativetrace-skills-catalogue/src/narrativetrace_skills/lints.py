# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A lints: schema/vocabulary hygiene over the whole catalogue, no LLM, seconds."""

from __future__ import annotations

import re

from narrativetrace_skills.pro_listing import ProListing
from narrativetrace_skills.skill import (
    COMMAND_VOCABULARY,
    CommandStep,
    Skill,
    SkillStep,
    command_strings,
    first_token,
    vocabulary_violations,
)

CATALOGUE_CHAR_BUDGET = 40_000
"""A conservative character-based proxy for the ~15k-token catalogue-wide budget: exceeding it
means skill descriptions are dropped SILENTLY by the runtime that loads them. No tokenizer
dependency: ~4 chars/token is a safe under-estimate of token count for English prose, so a char
budget well under 15k * 4 leaves margin on both sides of that approximation."""


def catalogue_description_chars(skills: tuple[Skill, ...]) -> int:
    return sum(len(skill.description) for skill in skills)


def catalogue_vocabulary_violations(skills: tuple[Skill, ...]) -> tuple[str, ...]:
    """Every ``commands`` string whose first token is outside the closed vocabulary, across the
    whole catalogue."""
    return tuple(violation for skill in skills for violation in vocabulary_violations(skill))


def allowed_tools_violations(skills: tuple[Skill, ...]) -> tuple[str, ...]:
    """Every declared ``allowed_tools`` entry that is not a bare command of the closed
    vocabulary: either a rendered platform spelling (``Bash(...)``, which belongs ONLY to
    ``render.claude.claude_tool_pattern``) or a command outside :data:`COMMAND_VOCABULARY`.

    Pins the split this catalogue depends on: the catalogue declares COMMANDS, the renderer
    spells them for the platform. A hand-written ``Bash(git *)`` here would render as
    ``Bash(Bash(git *) *)`` -- a rule matching nothing, in a field whose whole purpose is to
    match something."""
    violations: list[str] = []
    for skill in skills:
        for tool in skill.allowed_tools:
            if "(" in tool:
                violations.append(
                    f'{skill.canonical_name}: allowed tool "{tool}" is a rendered platform '
                    "spelling — declare the bare command and let the renderer spell it"
                )
            elif tool not in COMMAND_VOCABULARY:
                violations.append(
                    f'{skill.canonical_name}: allowed tool "{tool}" is outside the vocabulary'
                )
    return tuple(violations)


def unparseable_commands(skills: tuple[Skill, ...]) -> tuple[str, ...]:
    """Sanity companion to :func:`~narrativetrace_skills.skill.vocabulary_violations`: every
    command actually parses to a non-empty first token."""
    return tuple(
        f"{skill.canonical_name}: '{command}'"
        for skill in skills
        for command in command_strings(skill)
        if first_token(command) == ""
    )


def listings_disagreeing_with_feature_guide(
    listings: tuple[ProListing, ...], feature_guide_text: str
) -> tuple[str, ...]:
    """A Pro listing's recorded ``feature_guide_status_text`` must still appear verbatim in the
    feature guide's own text — catches the listing silently drifting out of sync with the doc it
    claims to summarize."""
    return tuple(
        listing.canonical_name
        for listing in listings
        if listing.feature_guide_status_text not in feature_guide_text
    )


_SECTION_MARK = "§"
_MD_FILENAME = re.compile(r"\b[\w.-]+\.md\b", re.IGNORECASE)


def _prose_of(skill: Skill) -> tuple[str, ...]:
    """Every prose string a rendered ``SKILL.md``/``AGENTS.md`` snippet actually shows for
    ``skill`` — never ``canonical_name`` (an identifier, not prose) and never a snippet step's
    resolved file content (real source, not the catalogue's own words)."""
    pieces: list[str] = [skill.description]
    if skill.when_to_use:
        pieces.append(skill.when_to_use)
    for step in skill.steps:
        pieces.extend(_step_prose(step))
    for rule in (*skill.always, *skill.never):
        pieces.extend([rule.rule, rule.reason])
    for section in skill.sections:
        pieces.extend([section.heading, section.markdown])
    return tuple(pieces)


def _step_prose(step: SkillStep) -> list[str]:
    """One step's shown prose: title, its optional lines, its commands and failure notes."""
    pieces = [step.title]
    pieces.extend(text for text in (step.flag, step.condition, step.done, step.verify) if text)
    if isinstance(step.body, CommandStep):
        pieces.extend(step.body.commands)
    for note in step.failure:
        pieces.extend([note.symptom, note.cause, note.fix])
    return pieces


def citation_violations(
    skill: Skill, repo_markdown_basenames: frozenset[str] = frozenset()
) -> tuple[str, ...]:
    """Tier A lint: no ``§`` section-mark citation, and no ``.md`` filename that isn't itself a
    real file in THIS repository, may appear in a skill's rendered prose. Catches a private
    planning-note citation before it ships in ``SKILL.md``/the ``AGENTS.md`` snippet — rationale
    sentences are fine, the citation naming the note is not. ``repo_markdown_basenames`` is
    injected (never real filesystem access in this module) so the lint stays a pure function over
    the catalogue, like every other one here; the caller supplies the real repo listing."""
    violations: list[str] = []
    for text in _prose_of(skill):
        if _SECTION_MARK in text:
            violations.append(f'{skill.canonical_name}: section-mark citation in "{text}"')
        for match in _MD_FILENAME.finditer(text):
            name = match.group(0)
            if name.lower() not in repo_markdown_basenames:
                violations.append(
                    f'{skill.canonical_name}: external filename citation "{name}" in "{text}"'
                )
    return tuple(violations)


_PUBLISHING_COMMANDS: tuple[re.Pattern[str], ...] = (re.compile(r"\bfeedback\b"),)
"""Commands that reach a channel where something becomes PUBLIC. Today that is the problem-report
verb (``narrativetrace feedback ...``). A tuple rather than one literal because a second
publishing command is a question somebody has to answer, not a regex somebody widens."""


def _executed_commands(skill: Skill) -> tuple[str, ...]:
    """Every string the agent RUNS for ``skill``: its steps' commands, then its steps' ``verify``
    commands -- a verify runs in the same turn, so it can publish exactly like a command does."""
    verifies = tuple(step.verify for step in skill.steps if step.verify)
    return (*command_strings(skill), *verifies)


def publishing_not_pre_approved(skills: tuple[Skill, ...]) -> tuple[str, ...]:
    """A skill whose steps can make something public must declare NO allowed tool that would
    pre-approve the command doing it.

    INTENT: the Claude flavour's ``allowed-tools`` grants its listed tools for the turn that LOADS
    the skill, without prompting. A reporting skill that declared ``uv`` would pre-approve its own
    reporting command and stop the harness asking exactly where asking is the product. One
    violation per publishing command or ``verify`` that runs one, in catalogue order (commands
    before verifies within a skill), naming the skill, the tool and the command."""
    return tuple(
        f'{skill.canonical_name}: declares allowed tool "{first_token(command)}", which '
        f'pre-approves its own publishing command "{command}" -- a skill that files something '
        "public must let the harness ask"
        for skill in skills
        for command in _executed_commands(skill)
        if any(pattern.search(command) for pattern in _PUBLISHING_COMMANDS)
        and first_token(command) in skill.allowed_tools
    )


_PROMOTING_COMMANDS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![\w-])narrativetrace-approve(?![\w-])"),
    re.compile(r"(?<![\w-])poe\s+approve(?![\w-])"),
)
"""The approve verb, in both spellings a page may use: the ``narrativetrace-approve`` console
script and the ``poe approve`` task. Running it IS the pinning — it turns every reviewed
``.received.nt`` into a committed ``.approved.nt``."""


def promotion_not_pre_approved(skills: tuple[Skill, ...]) -> tuple[str, ...]:
    """A skill whose steps promote an approval baseline must declare NO allowed tool that would
    pre-approve the promotion. Mirrors Java's ``promotionNotPreApproved``.

    INTENT: the pin is gated — show the whole ``.received.nt``, ask once, end the turn; the
    promotion runs only after the user's yes, in a later turn. A Claude-flavour ``allowed-tools``
    grants its tools for the turn that LOADS the skill, so a pinning skill that declared ``uv``
    would let the promotion run in the very turn the gate says must stop. One violation per
    promoting command or ``verify`` that runs one, naming the skill, the tool and the command."""
    return tuple(
        f'{skill.canonical_name}: declares allowed tool "{first_token(command)}", which '
        f'pre-approves its own promotion "{command}" -- a skill that pins a baseline must let '
        "the harness ask"
        for skill in skills
        for command in _executed_commands(skill)
        if any(pattern.search(command) for pattern in _PROMOTING_COMMANDS)
        and first_token(command) in skill.allowed_tools
    )
