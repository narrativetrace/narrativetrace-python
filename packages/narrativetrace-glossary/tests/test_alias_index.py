# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Behaviour of the deprecated-alias lookup a glossary induces.

Harvesting and violation reporting both ask "is this normalized phrase a deprecated alias here?",
so the answer is precomputed once per glossary. Matching is exact on the whole phrase and scoped
per context.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
    TermKey,
    TermKind,
    TermStatus,
    build_alias_index,
)
from narrativetrace_glossary.alias_index import _invariant as _index_invariant
from narrativetrace_glossary.models import _invariant

OVERDRAFT_ACCOUNT = GlossaryTerm(
    "overdraft account",
    "billing",
    TermKind.NOUN_PHRASE,
    TermStatus.CURATED,
    synonyms=[SynonymAlias("account with overdraft")],
    first_seen=date(2026, 8, 11),
)

GLOSSARY = Glossary(
    {"billing": BoundedContext("billing"), "support": BoundedContext("support")},
    [OVERDRAFT_ACCOUNT],
)


@pytest.fixture
def index() -> Iterator[Mapping[TermKey, GlossaryTerm]]:
    """Rechecks the source glossary at setup and teardown: an index is only as sound as it is."""
    assert _invariant(GLOSSARY), "the source glossary is inconsistent before the test"
    yield build_alias_index(GLOSSARY)
    assert _invariant(GLOSSARY), "the test left the source glossary inconsistent"


def test_finds_the_canonical_term_an_alias_is_deprecated_in_favour_of(
    index: Mapping[TermKey, GlossaryTerm],
) -> None:
    assert index[TermKey("billing", "account with overdraft")] is OVERDRAFT_ACCOUNT


def test_an_alias_is_recognized_only_in_the_context_that_declares_it(
    index: Mapping[TermKey, GlossaryTerm],
) -> None:
    assert TermKey("support", "account with overdraft") not in index


def test_a_canonical_term_is_not_an_alias_of_itself(index: Mapping[TermKey, GlossaryTerm]) -> None:
    assert TermKey("billing", "overdraft account") not in index


def test_matching_is_exact_so_neither_a_prefix_nor_an_extension_of_an_alias_hits(
    index: Mapping[TermKey, GlossaryTerm],
) -> None:
    assert TermKey("billing", "account with overdraft protection") not in index
    assert TermKey("billing", "account with") not in index


def test_a_glossary_declaring_no_synonyms_induces_an_empty_index() -> None:
    assert build_alias_index(Glossary()) == {}


def test_the_index_cannot_be_written_through(index: Mapping[TermKey, GlossaryTerm]) -> None:
    with pytest.raises(TypeError):
        index[TermKey("billing", "forged")] = OVERDRAFT_ACCOUNT  # type: ignore[index]


def test_rejects_a_glossary_that_is_not_one() -> None:
    with pytest.raises(TypeError, match=r"\Aglossary must be a Glossary\Z"):
        build_alias_index([OVERDRAFT_ACCOUNT])  # type: ignore[arg-type]


def test_an_index_entry_filed_under_the_wrong_context_or_phrase_is_inconsistent() -> None:
    assert _index_invariant({TermKey("billing", "account with overdraft"): OVERDRAFT_ACCOUNT})
    assert not _index_invariant(
        {TermKey("support", "account with overdraft"): OVERDRAFT_ACCOUNT}
    ), "an alias filed outside its term's context would suppress someone else's harvest"
    assert not _index_invariant({TermKey("billing", "overdraft account"): OVERDRAFT_ACCOUNT}), (
        "a phrase the term does not deprecate is no alias of it"
    )
