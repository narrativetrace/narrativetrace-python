# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Lookup from ``(context, normalized alias)`` to the canonical term that deprecates it.

``AliasIndex``, whose three methods collapse into one function returning a read-only
mapping: ``key in index`` answers Java's ``isAlias`` and ``index.get(key)`` answers its
``canonicalFor``. INTENT: harvesting and violation reporting both ask the same question, so the
answer is precomputed once per glossary.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from narrativetrace_glossary.models import Glossary, GlossaryTerm, TermKey


def build_alias_index(glossary: Glossary) -> Mapping[TermKey, GlossaryTerm]:
    """Indexes every ``(term context, synonym alias)`` pair the glossary declares.

    Matching is exact on the whole normalized phrase — neither a substring nor a superstring of an
    alias is one — and scoped per context, so an alias is recognized only where its canonical term
    is defined.

    Returns:
        A read-only mapping; a phrase absent from it is not a deprecated alias.

    Raises:
        TypeError: if ``glossary`` is not a :class:`Glossary`.
    """
    if not isinstance(glossary, Glossary):
        raise TypeError("glossary must be a Glossary")
    index = MappingProxyType(
        {
            TermKey(term.context, synonym.alias): term
            for term in glossary.terms
            for synonym in term.synonyms
        }
    )
    assert _invariant(index), "every indexed key must name an alias of the term it maps to"
    return index


def _invariant(index: Mapping[TermKey, GlossaryTerm]) -> bool:
    """Returns whether an index is consistent with the terms it points at.

    Every key must be filed under its canonical term's own context and name a phrase that term
    actually deprecates — otherwise a lookup would suppress a harvest on someone else's behalf.
    """
    return all(
        key.context == term.context
        and any(synonym.alias == key.normalized for synonym in term.synonyms)
        for key, term in index.items()
    )
