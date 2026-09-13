# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A lints: schema/vocabulary hygiene over the whole catalogue, no LLM, seconds."""

from __future__ import annotations

import re

from narrativetrace_skills.pro_listing import ProListing
from narrativetrace_skills.skill import (
    CommandStep,
    Skill,
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
        pieces.append(step.title)
        if step.flag:
            pieces.append(step.flag)
        if step.verify:
            pieces.append(step.verify)
        if isinstance(step.body, CommandStep):
            pieces.extend(step.body.commands)
        for note in step.failure:
            pieces.extend([note.symptom, note.cause, note.fix])
    for rule in (*skill.always, *skill.never):
        pieces.extend([rule.rule, rule.reason])
    return tuple(pieces)


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
