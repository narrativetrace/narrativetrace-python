# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Behaviour of carrying curated glossary entries across a normalization rule change."""

from __future__ import annotations

from datetime import date

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    HarvestCandidate,
    TermKind,
    TermStatus,
)
from narrativetrace_glossary.rekey import migrate

SEEN = date(2026, 8, 15)


def _glossary(*terms: GlossaryTerm) -> Glossary:
    return Glossary({"library": BoundedContext("library", ["acme.library"])}, list(terms))


def _term(
    phrase: str,
    kind: TermKind,
    translations: dict[str, str],
    *sources: str,
) -> GlossaryTerm:
    return GlossaryTerm(
        phrase,
        "library",
        kind,
        TermStatus.CURATED if translations else TermStatus.HARVESTED,
        translations=translations,
        sources=sources,
        first_seen=SEEN,
    )


def _harvest(*phrases: str) -> tuple[HarvestCandidate, ...]:
    return tuple(
        HarvestCandidate("library", phrase, TermKind.WORD, "Book.site", "site")
        for phrase in phrases
    )


def test_a_curated_property_read_moves_to_the_noun_it_reads_with_its_translation_intact() -> None:
    glossary = _glossary(
        _term("get author", TermKind.VERB_PHRASE, {"es": "autor"}, "Book.getAuthor")
    )

    migrated = migrate(glossary, _harvest("author"))

    assert len(migrated.terms) == 1
    term = migrated.terms[0]
    assert term.term == "author"
    assert term.kind is TermKind.WORD
    assert term.translations["es"] == "autor"


def test_a_moved_entry_merges_into_the_successor_that_already_exists() -> None:
    glossary = _glossary(
        _term("author", TermKind.WORD, {"es": "autor"}, "Book.getAuthor"),
        _term("get author", TermKind.VERB_PHRASE, {"de": "Autor"}, "Book.getAuthor"),
    )

    migrated = migrate(glossary, _harvest("author"))

    assert len(migrated.terms) == 1
    term = migrated.terms[0]
    assert term.term == "author"
    assert term.translations["es"] == "autor"
    assert term.translations["de"] == "Autor"
    assert term.sources == ("Book.getAuthor",)


def test_an_object_noun_starting_with_a_function_word_moves_to_what_is_left_of_it() -> None:
    glossary = _glossary(
        _term("per night", TermKind.NOUN_PHRASE, {"es": "por noche"}, "Room.pricePerNight")
    )

    migrated = migrate(glossary, _harvest("night"))

    assert len(migrated.terms) == 1
    term = migrated.terms[0]
    assert term.term == "night"
    assert term.translations["es"] == "por noche"


def test_a_term_whose_every_source_was_language_plumbing_retires() -> None:
    glossary = _glossary(
        _term("copy", TermKind.VERB_PHRASE, {"es": "ejemplar"}, "Book.copy", "Member.copy"),
        _term("component 1", TermKind.NOUN_PHRASE, {}, "Book.component1"),
        _term("value of", TermKind.VERB_PHRASE, {}, "CustomerTier.valueOf"),
    )

    migrated = migrate(glossary, _harvest("author"))

    assert migrated.terms == ()


def test_a_phrase_the_harvest_still_produces_is_never_moved() -> None:
    """The near miss: a phrase the harvest still produces is current, whatever it begins with."""
    glossary = _glossary(
        _term(
            "get or create account",
            TermKind.VERB_PHRASE,
            {"es": "obtener o crear cuenta"},
            "Ledger.getOrCreateAccount",
        )
    )

    migrated = migrate(glossary, _harvest("get or create account"))

    assert [term.term for term in migrated.terms] == ["get or create account"]


def test_a_term_whose_successor_the_harvest_does_not_produce_stays_where_it_is() -> None:
    glossary = _glossary(
        _term("get author", TermKind.VERB_PHRASE, {"es": "autor"}, "Book.getAuthor")
    )

    migrated = migrate(glossary, _harvest("title"))

    assert [term.term for term in migrated.terms] == ["get author"]


def test_a_term_whose_code_was_simply_deleted_is_kept() -> None:
    glossary = _glossary(_term("overdraft", TermKind.WORD, {"es": "descubierto"}, "Old.x"))

    migrated = migrate(glossary, _harvest("author"))

    assert [term.term for term in migrated.terms] == ["overdraft"]


def test_rejects_a_non_glossary_input() -> None:
    with pytest.raises(TypeError, match=r"\Aglossary must be a Glossary\Z"):
        migrate(None, _harvest())  # type: ignore[arg-type]
