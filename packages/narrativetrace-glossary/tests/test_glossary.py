# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Structural invariants of the whole-glossary aggregate."""

from __future__ import annotations

from datetime import date

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
    TermKind,
    TermStatus,
)
from narrativetrace_glossary.models import _invariant

FIRST_SEEN = date(2026, 8, 11)


def term(text: str, context: str = "billing", **overrides: object) -> GlossaryTerm:
    fields: dict[str, object] = {
        "term": text,
        "context": context,
        "kind": TermKind.NOUN_PHRASE,
        "status": TermStatus.HARVESTED,
        "first_seen": FIRST_SEEN,
    }
    fields.update(overrides)
    return GlossaryTerm(**fields)  # type: ignore[arg-type]


def contexts(*names: str) -> dict[str, BoundedContext]:
    return {name: BoundedContext(name) for name in names}


def test_empty_glossary_is_valid_and_carries_the_current_schema_version() -> None:
    glossary = Glossary()

    assert glossary.schema_version == 1
    assert glossary.contexts == {}
    assert glossary.terms == ()


def test_terms_are_canonicalized_to_context_then_term_order() -> None:
    glossary = Glossary(
        contexts("billing", "shipping"),
        [
            term("refund"),
            term("crate", "shipping"),
            term("invoice"),
            term("bill of lading", "shipping"),
        ],
    )

    assert [(entry.context, entry.term) for entry in glossary.terms] == [
        ("billing", "invoice"),
        ("billing", "refund"),
        ("shipping", "bill of lading"),
        ("shipping", "crate"),
    ]


def test_two_glossaries_with_the_same_vocabulary_are_equal_regardless_of_insertion_order() -> None:
    first = Glossary(contexts("billing"), [term("invoice"), term("refund")])
    second = Glossary(contexts("billing"), [term("refund"), term("invoice")])

    assert first == second


def test_the_same_term_text_in_two_contexts_is_two_distinct_entries() -> None:
    glossary = Glossary(
        contexts("billing", "shipping"), [term("account"), term("account", "shipping")]
    )

    assert len(glossary.terms) == 2


def test_duplicate_term_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Aduplicate term key: billing/invoice\Z"):
        Glossary(contexts("billing"), [term("invoice"), term("invoice", status=TermStatus.CURATED)])


def test_a_term_in_an_undeclared_context_is_rejected() -> None:
    with pytest.raises(
        ValueError, match=r"\Aterm 'crate' references undeclared context 'shipping'\Z"
    ):
        Glossary(contexts("billing"), [term("crate", "shipping")])


def test_an_alias_equal_to_a_canonical_term_of_the_same_context_is_rejected() -> None:
    canonical = term("overdraft account", synonyms=[SynonymAlias("account with overdraft")])

    with pytest.raises(
        ValueError,
        match=r"\Aalias 'account with overdraft' equals a canonical term in context 'billing'\Z",
    ):
        Glossary(contexts("billing"), [canonical, term("account with overdraft")])


def test_an_alias_may_equal_a_canonical_term_of_a_different_context() -> None:
    canonical = term("overdraft account", synonyms=[SynonymAlias("account with overdraft")])

    glossary = Glossary(
        contexts("billing", "shipping"), [canonical, term("account with overdraft", "shipping")]
    )

    assert len(glossary.terms) == 2


def test_a_context_filed_under_a_key_that_is_not_its_name_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Acontext 'shipping' is filed under key 'billing'\Z"):
        Glossary({"billing": BoundedContext("shipping")})


@pytest.mark.parametrize("version", [0, -1])
def test_a_schema_version_below_one_is_rejected(version: int) -> None:
    with pytest.raises(ValueError, match=r"\Aschema_version must be at least 1: "):
        Glossary(schema_version=version)


def test_a_glossary_declaring_abbreviations_is_stamped_at_the_schema_that_introduced_them() -> None:
    glossary = Glossary(abbreviations={"fx": "foreign exchange"})

    assert glossary.schema_version == 2
    assert dict(glossary.abbreviations) == {"fx": "foreign exchange"}


def test_a_glossary_declaring_no_abbreviations_stays_at_the_base_schema_version() -> None:
    glossary = Glossary(contexts("billing"), [term("invoice")])

    assert glossary.schema_version == 1
    assert glossary.abbreviations == {}


def test_a_schema_version_above_the_one_abbreviations_require_is_kept() -> None:
    glossary = Glossary(abbreviations={"fx": "foreign exchange"}, schema_version=7)

    assert glossary.schema_version == 7


def test_a_blank_abbreviation_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Aabbreviation must not be blank\Z"):
        Glossary(abbreviations={"   ": "foreign exchange"})


def test_a_blank_expansion_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Aabbreviation 'fx' has a blank expansion\Z"):
        Glossary(abbreviations={"fx": "   "})


def test_abbreviations_reject_in_place_mutation() -> None:
    glossary = Glossary(abbreviations={"fx": "foreign exchange"})

    with pytest.raises(TypeError):
        glossary.abbreviations["calc"] = "calculate"  # type: ignore[index]


def test_contexts_reject_in_place_mutation() -> None:
    glossary = Glossary(contexts("billing"))

    with pytest.raises(TypeError):
        glossary.contexts["shipping"] = BoundedContext("shipping")  # type: ignore[index]


def corrupted(glossary: Glossary, field: str, value: object) -> Glossary:
    """Writes past the frozen dataclass, reproducing state no constructor could produce."""
    object.__setattr__(glossary, field, value)
    return glossary


def test_the_invariant_holds_for_every_constructed_glossary() -> None:
    assert _invariant(Glossary(contexts("billing"), [term("invoice"), term("refund")]))


def test_the_invariant_fails_when_term_order_is_corrupted_behind_the_constructor() -> None:
    glossary = Glossary(contexts("billing"), [term("invoice"), term("refund")])

    assert not _invariant(corrupted(glossary, "terms", tuple(reversed(glossary.terms))))


def test_the_invariant_fails_when_the_schema_version_is_corrupted_behind_the_constructor() -> None:
    glossary = Glossary(contexts("billing"), [term("invoice")])

    assert not _invariant(corrupted(glossary, "schema_version", 0))


def test_the_invariant_fails_when_abbreviations_outrun_the_schema_version() -> None:
    glossary = Glossary(abbreviations={"fx": "foreign exchange"})

    assert not _invariant(corrupted(glossary, "schema_version", 1))


def test_the_invariant_fails_when_a_blank_abbreviation_is_written_behind_the_constructor() -> None:
    glossary = Glossary(abbreviations={"fx": "foreign exchange"})

    assert not _invariant(corrupted(glossary, "abbreviations", {"fx": ""}))


def test_the_invariant_fails_when_a_terms_context_is_corrupted_behind_the_constructor() -> None:
    glossary = Glossary(contexts("billing"), [term("invoice")])

    assert not _invariant(corrupted(glossary, "terms", (term("invoice", "shipping"),)))


def test_a_glossary_is_a_container_not_a_hashable_value() -> None:
    with pytest.raises(TypeError, match=r"unhashable"):
        hash(Glossary())
