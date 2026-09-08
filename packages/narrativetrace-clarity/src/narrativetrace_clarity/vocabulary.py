# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The vocabulary one project has declared to be its own, as the clarity scorers see it.

``DomainVocabulary``. It makes the built-in dictionaries extensible per project without
a second configuration file: a repository's committed glossary (ADR-012) is the single vocabulary
source, the glossary package maps it onto this type, and every dictionary consults it beside its
own tiers. Clarity therefore teaches in the project's own language instead of scoring its domain
words as unknown.

Three rules are deliberate and load-bearing. **Only single tokens count** — the scorers tokenize
identifiers, so a multi-word glossary phrase (``credit tranche``) can never match one token and is
dropped at construction rather than silently never matching. **The built-in dictionaries keep
their authority** — this type answers questions, it does not override answers; each dictionary
decides where the project vocabulary sits in its own precedence order, and none lets a project
promote a generic word to domain vocabulary. **Accepted shorthand is its own set** — it comes only
from the glossary's ``abbreviations`` section, never from the tokens of a canonical
term, so accepting an abbreviation stays a decision somebody made and read.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


def _single_tokens(terms: Iterable[str]) -> frozenset[str]:
    return frozenset(
        normalized
        for normalized in (term.strip().lower() for term in terms)
        if normalized and " " not in normalized
    )


@dataclass(frozen=True, slots=True)
class DomainVocabulary:
    """Lowercase single tokens a project declares in its committed glossary, in three sets.

    ``verbs`` and ``nouns`` come from its canonical terms; ``abbreviations`` from the glossary's
    own accepted-shorthand section, which is a separate human decision. An empty vocabulary is the
    normal state: a project without a committed glossary scores exactly as it did before this type
    existed.
    """

    verbs: frozenset[str] = frozenset()
    nouns: frozenset[str] = frozenset()
    abbreviations: frozenset[str] = frozenset()

    @classmethod
    def of(
        cls, verbs: Iterable[str], nouns: Iterable[str], abbreviations: Iterable[str] = ()
    ) -> DomainVocabulary:
        """Builds a vocabulary from raw declared terms, keeping only the single-token ones."""
        return cls(_single_tokens(verbs), _single_tokens(nouns), _single_tokens(abbreviations))

    def is_empty(self) -> bool:
        """Whether the project declared nothing this vocabulary can answer for."""
        return not self.verbs and not self.nouns and not self.abbreviations

    def is_domain_verb(self, token: str) -> bool:
        """Whether the project declared this token as one of its verbs."""
        return token.lower() in self.verbs

    def is_domain_noun(self, token: str) -> bool:
        """Whether the project declared this token as one of its nouns."""
        return token.lower() in self.nouns

    def is_accepted_abbreviation(self, token: str) -> bool:
        """Whether the project's glossary lists this token as accepted shorthand.

        Only the glossary's ``abbreviations`` section answers yes. Appearing as a token of a
        canonical term does not: committing the phrase ``calc total`` is a statement about the
        domain's nouns, not a decision that ``calc`` never needs spelling out — and reading it as
        one silently dropped the ``calc`` → ``calculate`` hint for the whole repository.
        """
        return token.lower() in self.abbreviations


EMPTY = DomainVocabulary()
"""The vocabulary of a project that has declared none — the default everywhere."""
