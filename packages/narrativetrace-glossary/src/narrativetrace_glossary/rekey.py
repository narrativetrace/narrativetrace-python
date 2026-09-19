# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Carries curated entries across a change to normalization, before the harvest is merged.

``migrate``. INTENT: term identity is the normalized phrase, so any change to
normalization strands curated entries under a key nothing will look up again. This moves them: a
term whose successor the harvest now produces takes that key, definition and translations intact,
and a term whose every source was language plumbing retires. Everything else is untouched -- the
glossary is otherwise additive, and a term whose code was merely deleted stays exactly where it is.

Both halves are decided against the harvest, never against a term's text alone. A phrase the
harvest still produces is current by definition and never moves, which is what keeps an honest
``getOrCreateAccount`` out of the property-read rule; and a phrase the harvest does not produce is
not a successor, so no key is ever invented.

Divergence from Java: this runtime's own scanners never emit a source naming a compiler-synthesized
member (Kotlin's ``copy``/``componentN``, a JVM enum's ``values``/``valueOf`` have no Python
analogue -- see :mod:`narrativetrace_glossary.static_scan`, which already skips every ``_``-prefixed
member). The plumbing-retirement rule is ported anyway, unconditionally, because ``migrate`` is a
general glossary-migration utility, not a fix specific to those two Java defects: it must carry a
committed glossary that could hold anything, whatever tool or runtime last wrote it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from narrativetrace_glossary.harvester import HarvestCandidate
from narrativetrace_glossary.models import Glossary, GlossaryTerm, TermKey, TermKind, TermStatus

_PLUMBING_MEMBERS = frozenset({"values", "valueOf", "copy"})
"""Members a language writes for you: nothing they named is anyone's vocabulary."""

_COMPONENT_ACCESSOR = re.compile(r"component\d+")

_RETIRED_HEADS = ("get ", "is ", "per ")
"""Phrase heads a rule change drops, each leaving the rest of the phrase as the successor."""


def migrate(glossary: Glossary, candidates: Sequence[HarvestCandidate]) -> Glossary:
    """Re-keys the glossary against what the harvest now produces.

    Args:
        glossary: the committed glossary as read.
        candidates: the current run's observations.

    Returns:
        The glossary with retired keys carried to their successors.

    Raises:
        TypeError: if ``glossary`` is not a :class:`Glossary`.
    """
    if not isinstance(glossary, Glossary):
        raise TypeError("glossary must be a Glossary")
    produced = {TermKey(candidate.context, candidate.phrase) for candidate in candidates}
    carried: dict[TermKey, GlossaryTerm] = {}
    for term in glossary.terms:
        kept = _fate_of(term, produced)
        if kept is None:
            continue
        key = TermKey.of(kept)
        carried[key] = _combine(carried[key], kept) if key in carried else kept
    return Glossary(glossary.contexts, list(carried.values()), glossary.abbreviations)


def _fate_of(term: GlossaryTerm, produced: set[TermKey]) -> GlossaryTerm | None:
    """The term as it survives, or ``None`` when nothing will ever produce it again."""
    if TermKey.of(term) in produced:
        return term
    if _was_language_plumbing(term):
        return None
    phrase = _successor_phrase(term)
    if phrase is not None and TermKey(term.context, phrase) in produced:
        return _under_phrase(term, phrase)
    return term


def _successor_phrase(term: GlossaryTerm) -> str | None:
    """The phrase this term's identifier normalizes to now, when a rule change moved it.

    A property read only moves when a source of the term actually was one: ``get`` at the head of
    a phrase can be the verb someone wrote. Template terms are raw annotation/decorator text and
    are never normalized, so no head rule applies to them.
    """
    if term.kind is TermKind.TEMPLATE:
        return None
    for head in _RETIRED_HEADS:
        if term.term.startswith(head) and (head == "per " or _reads_a_property(term)):
            return term.term[len(head) :]
    return None


def _reads_a_property(term: GlossaryTerm) -> bool:
    return any(_member_of(source).startswith(("get", "is")) for source in term.sources)


def _was_language_plumbing(term: GlossaryTerm) -> bool:
    return bool(term.sources) and all(_is_plumbing(_member_of(source)) for source in term.sources)


def _is_plumbing(member: str) -> bool:
    return member in _PLUMBING_MEMBERS or bool(_COMPONENT_ACCESSOR.fullmatch(member))


def _member_of(source: str) -> str:
    return source.rpartition(".")[2]


def _under_phrase(term: GlossaryTerm, phrase: str) -> GlossaryTerm:
    """The same entry under its new key; the phrase a property read leaves behind is a noun."""
    kind = TermKind.WORD if " " not in phrase else TermKind.NOUN_PHRASE
    return GlossaryTerm(
        phrase,
        term.context,
        kind,
        term.status,
        term.definition,
        term.translations,
        term.synonyms,
        term.sources,
        first_seen=term.first_seen,
    )


def _combine(kept: GlossaryTerm, arriving: GlossaryTerm) -> GlossaryTerm:
    """The surviving entry keeps everything it has and gains what the retired key carried."""
    translations = dict(arriving.translations)
    translations.update(kept.translations)
    synonyms = list(kept.synonyms)
    synonyms.extend(alias for alias in arriving.synonyms if alias not in synonyms)
    sources = list(kept.sources)
    sources.extend(source for source in arriving.sources if source not in sources)
    return GlossaryTerm(
        kept.term,
        kept.context,
        kept.kind,
        arriving.status if kept.status is TermStatus.HARVESTED else kept.status,
        kept.definition if kept.definition is not None else arriving.definition,
        translations,
        synonyms,
        sources,
        first_seen=min(kept.first_seen, arriving.first_seen),
    )
