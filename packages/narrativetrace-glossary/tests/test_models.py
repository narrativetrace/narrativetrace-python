# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Behaviour of the glossary value model."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    GlossaryTerm,
    SynonymAlias,
    TermKey,
    TermKind,
    TermStatus,
)

FIRST_SEEN = date(2026, 8, 11)


def test_term_kinds_carry_their_kebab_case_json_labels() -> None:
    assert [kind.value for kind in TermKind] == ["word", "noun-phrase", "verb-phrase", "template"]


def test_term_statuses_carry_their_lowercase_json_labels() -> None:
    assert [status.value for status in TermStatus] == ["harvested", "curated", "stale"]


def test_synonym_alias_keeps_its_optional_curator_note() -> None:
    alias = SynonymAlias("account with overdraft", "legacy v1 API phrasing")

    assert alias.alias == "account with overdraft"
    assert alias.note == "legacy v1 API phrasing"


def test_synonym_alias_defaults_to_no_note() -> None:
    assert SynonymAlias("account with overdraft").note is None


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_synonym_alias_rejects_a_blank_alias(blank: str) -> None:
    with pytest.raises(ValueError, match=r"\Aalias must not be blank\Z"):
        SynonymAlias(blank)


def test_bounded_context_freezes_declared_prefixes_against_caller_mutation() -> None:
    declared = ["acme.billing", "acme.invoicing"]

    context = BoundedContext("billing", declared, "Charging, invoicing, funds")
    declared.append("acme.shipping")

    assert context.packages == ("acme.billing", "acme.invoicing")


def test_bounded_context_defaults_to_no_prefixes_and_no_description() -> None:
    context = BoundedContext("_unassigned")

    assert context.packages == ()
    assert context.description is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_bounded_context_rejects_a_blank_name(blank: str) -> None:
    with pytest.raises(ValueError, match=r"\Acontext name must not be blank\Z"):
        BoundedContext(blank)


def _term(**overrides: object) -> GlossaryTerm:
    fields: dict[str, object] = {
        "term": "overdraft account",
        "context": "billing",
        "kind": TermKind.NOUN_PHRASE,
        "status": TermStatus.HARVESTED,
        "first_seen": date(2026, 8, 11),
    }
    fields.update(overrides)
    return GlossaryTerm(**fields)  # type: ignore[arg-type]


def test_term_freezes_human_owned_collections_against_caller_mutation() -> None:
    translations = {"es": "cuenta con descubierto"}
    synonyms = [SynonymAlias("account with overdraft")]
    sources = ["billing.overdraft_service.open_overdraft_account"]

    term = _term(translations=translations, synonyms=synonyms, sources=sources)
    translations["fr"] = "compte à découvert"
    synonyms.append(SynonymAlias("overdrawn account"))
    sources.append("billing.other")

    assert term.translations == {"es": "cuenta con descubierto"}
    assert term.synonyms == (SynonymAlias("account with overdraft"),)
    assert term.sources == ("billing.overdraft_service.open_overdraft_account",)


def test_term_translations_reject_in_place_mutation() -> None:
    term = _term(translations={"es": "cuenta con descubierto"})

    with pytest.raises(TypeError):
        term.translations["es"] = "otra cosa"  # type: ignore[index]


def test_term_defaults_leave_every_human_owned_field_empty() -> None:
    term = _term()

    assert term.definition is None
    assert term.translations == {}
    assert term.synonyms == ()
    assert term.sources == ()


@pytest.mark.parametrize("blank", ["", "  "])
def test_term_rejects_a_blank_term(blank: str) -> None:
    with pytest.raises(ValueError, match=r"\Aterm must not be blank\Z"):
        _term(term=blank)


@pytest.mark.parametrize("blank", ["", "  "])
def test_term_rejects_a_blank_context(blank: str) -> None:
    with pytest.raises(ValueError, match=r"\Acontext must not be blank\Z"):
        _term(context=blank)


def test_term_rejects_a_timestamp_where_a_calendar_date_is_required() -> None:
    with pytest.raises(TypeError, match=r"\Afirst_seen must be a date, not datetime\Z"):
        _term(first_seen=datetime(2026, 8, 11, 12, 0, tzinfo=UTC))


def test_term_key_identifies_a_term_by_context_and_text() -> None:
    assert TermKey.of(_term()) == TermKey("billing", "overdraft account")


def test_term_key_of_the_same_text_in_two_contexts_are_distinct_and_hashable() -> None:
    billing = TermKey.of(_term())
    shipping = TermKey.of(_term(context="shipping"))

    assert {billing, shipping} == {
        TermKey("billing", "overdraft account"),
        TermKey("shipping", "overdraft account"),
    }


def test_a_term_is_hashable_so_it_can_join_a_set_of_terms() -> None:
    plain = GlossaryTerm(
        "overdraft account",
        "billing",
        TermKind.NOUN_PHRASE,
        TermStatus.HARVESTED,
        first_seen=FIRST_SEEN,
    )
    translated = GlossaryTerm(
        "overdraft account",
        "billing",
        TermKind.NOUN_PHRASE,
        TermStatus.HARVESTED,
        translations={"es": "cuenta con descubierto"},
        first_seen=FIRST_SEEN,
    )

    assert len({plain, translated}) == 2
    assert hash(plain) == hash(translated), "equal identity must hash equal, whatever else differs"


def test_two_equal_terms_hash_alike() -> None:
    def build() -> GlossaryTerm:
        return GlossaryTerm(
            "overdraft account",
            "billing",
            TermKind.NOUN_PHRASE,
            TermStatus.HARVESTED,
            translations={"es": "cuenta con descubierto"},
            first_seen=FIRST_SEEN,
        )

    assert build() == build()
    assert len({build(), build()}) == 1
