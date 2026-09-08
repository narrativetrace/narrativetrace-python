# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Dictionary of abbreviations that reduce naming clarity (mgr, impl, util, ...).

``AbbreviationDictionary`` — 187 entries in three tiers (universal 0.8, well-known 0.6,
ambiguous 0.3), byte-identical to the Java source (see ``_abbreviations_data``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from narrativetrace_clarity import _abbreviations_data as _data
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary


class Tier(Enum):
    """Abbreviation clarity tiers."""

    UNIVERSAL = "UNIVERSAL"
    WELL_KNOWN = "WELL_KNOWN"
    AMBIGUOUS = "AMBIGUOUS"


_TIER_SCORES = {Tier.UNIVERSAL: 0.8, Tier.WELL_KNOWN: 0.6, Tier.AMBIGUOUS: 0.3}


@dataclass(frozen=True, slots=True)
class Entry:
    """A recognized abbreviation with its tier, score, and expansion."""

    tier: Tier
    score: float
    expansion: str


_ABBREVIATIONS: dict[str, Entry] = {
    abbr: Entry(Tier[tier], _TIER_SCORES[Tier[tier]], expansion)
    for abbr, (tier, expansion) in _data.ABBREVIATIONS.items()
}

assert len(_ABBREVIATIONS) == 187


def lookup(token: str, vocabulary: DomainVocabulary = EMPTY) -> Entry | None:
    """Returns the abbreviation entry for ``token``, or ``None`` if not an abbreviation.

    A token listed in the project's glossary ``abbreviations`` section returns ``None`` — the same
    answer as a word the dictionary never knew. Callers already treat ``None`` as "not an
    abbreviation", so accepted shorthand is neither scored down nor asked to be spelled out.

    Only that section accepts. A token that merely appears inside a canonical term still counts as
    an abbreviation: committing the noun phrase ``calc total`` says nothing about whether ``calc``
    is accepted shorthand.
    """
    lower = token.lower()
    if vocabulary.is_accepted_abbreviation(lower):
        return None
    return _ABBREVIATIONS.get(lower)
