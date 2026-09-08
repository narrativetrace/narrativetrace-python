# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Classifies verbs as domain-specific, standard, generic, or boolean prefixes.

``VerbDictionary``. The domain set is the union of 34 industry/technical category sets
(828 unique verbs). Generic∩Domain = ∅ and Boolean∩Domain = ∅ are enforced at import, mirroring
Java's static guard. Dictionary data is byte-identical to the Java source (see ``_verbs_data``).
"""

from __future__ import annotations

from enum import Enum

from narrativetrace_clarity import _verbs_data as _data
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary


class Category(Enum):
    """Verb categories in Java's priority order."""

    DOMAIN = "DOMAIN"
    STANDARD = "STANDARD"
    GENERIC = "GENERIC"
    BOOLEAN_PREFIX = "BOOLEAN_PREFIX"
    UNKNOWN = "UNKNOWN"


DOMAIN_VERBS: frozenset[str] = frozenset(
    verb for verbs in _data.DOMAIN_CATEGORIES.values() for verb in verbs
)
STANDARD_VERBS: frozenset[str] = frozenset(_data.STANDARD_VERBS)
GENERIC_VERBS: frozenset[str] = frozenset(_data.GENERIC_VERBS)
BOOLEAN_PREFIXES: frozenset[str] = frozenset(_data.BOOLEAN_PREFIXES)

# Java size-floor guards: fail loudly if the extracted data ever shrinks.
assert len(_data.DOMAIN_CATEGORIES) == 34
assert len(DOMAIN_VERBS) == 828
assert len(STANDARD_VERBS) == 197
assert len(GENERIC_VERBS) == 21
assert len(BOOLEAN_PREFIXES) == 17


def _enforce_no_overlap(left_name: str, left: frozenset[str], right: frozenset[str]) -> None:
    overlap = sorted(left & right)
    if overlap:
        raise ValueError(f"Verb dictionary overlap between {left_name} and DOMAIN_VERBS: {overlap}")


_enforce_no_overlap("GENERIC_VERBS", GENERIC_VERBS, DOMAIN_VERBS)
_enforce_no_overlap("BOOLEAN_PREFIXES", BOOLEAN_PREFIXES, DOMAIN_VERBS)
# Load-bearing since the project vocabulary landed: ``categorize`` decides generic before the
# project's own verbs (so a glossary cannot promote ``process``), which puts generic ahead of
# standard. That reordering is behaviour-preserving only while these two tiers are disjoint.
_enforce_no_overlap("GENERIC_VERBS", GENERIC_VERBS, STANDARD_VERBS)


def categorize(verb: str, vocabulary: DomainVocabulary = EMPTY) -> tuple[Category, float]:
    """Returns the (category, score) for a verb, in Java's precedence order.

    Boolean prefixes, built-in domain verbs and generic verbs are decided first, so a project
    cannot promote ``process`` or ``is`` by committing them to its glossary — generic stays
    generic. What a project can do is claim a word the built-in dictionaries would score as merely
    standard or unknown: in its domain, ``fold`` and ``send`` are domain verbs.
    """
    lower = verb.lower()
    if lower in BOOLEAN_PREFIXES:
        return Category.BOOLEAN_PREFIX, 1.0
    if lower in DOMAIN_VERBS:
        return Category.DOMAIN, 1.0
    if lower in GENERIC_VERBS:
        return Category.GENERIC, 0.4
    if vocabulary.is_domain_verb(lower):
        return Category.DOMAIN, 1.0
    if lower in STANDARD_VERBS:
        return Category.STANDARD, 0.8
    return Category.UNKNOWN, 0.3
