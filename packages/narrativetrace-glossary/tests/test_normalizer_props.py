# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for the normalization safety properties.

Plan section 10 makes convergence binding: every spelling of the same words must produce one
phrase, and normalizing an already-normalized phrase must change nothing — otherwise a second
harvest re-keys terms the first harvest wrote, and merges stop being idempotent.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from narrativetrace_glossary import (
    TermCandidate,
    class_candidate,
    exception_candidate,
    method_candidates,
    normalize_phrase,
    parameter_candidate,
)
from narrativetrace_glossary.normalizer import _invariant

# Words chosen to exercise every singularization rule at once: regular plurals, -ies, sibilant
# -es stems, -se plurals, s-final singulars, invariant plurals, verbs, and function words.
WORDS = [
    "account", "overdraft", "with", "payment", "plans", "entries", "status", "boxes", "customer",
    "charge", "insufficient", "funds", "limit", "for", "aliases", "gases", "series", "cases",
    "responses", "lenses", "news", "species", "always", "addresses", "matches", "houses",
]  # fmt: skip

TOKENS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12)
WORD_LISTS = st.lists(st.sampled_from(WORDS), min_size=1, max_size=4)


def capitalize(word: str) -> str:
    """Upper-cases the first character only — ``str.capitalize`` would lower-case the rest."""
    return word[0].upper() + word[1:]


def camel_case(words: list[str]) -> str:
    return words[0] + "".join(capitalize(word) for word in words[1:])


@given(words=WORD_LISTS)
def test_camel_pascal_and_snake_spellings_of_the_same_words_converge(words: list[str]) -> None:
    camel = camel_case(words)

    from_camel = normalize_phrase(camel)

    assert normalize_phrase(capitalize(camel)) == from_camel
    assert normalize_phrase("_".join(words)) == from_camel
    assert from_camel == from_camel.lower()


@given(words=WORD_LISTS)
def test_normalizing_an_already_normalized_phrase_changes_nothing(words: list[str]) -> None:
    once = normalize_phrase(camel_case(words))

    assert normalize_phrase(once.replace(" ", "_")) == once


@given(token=TOKENS)
def test_normalization_is_idempotent_on_an_arbitrary_token(token: str) -> None:
    once = normalize_phrase(token)

    assert normalize_phrase(once.replace(" ", "_")) == once


@given(token=TOKENS)
def test_normalization_never_erases_a_token(token: str) -> None:
    assert normalize_phrase(token).strip()


@given(words=WORD_LISTS)
def test_every_harvested_candidate_matches_the_shape_its_kind_claims(words: list[str]) -> None:
    identifier = camel_case(words)

    produced: list[TermCandidate | None] = [
        *method_candidates(identifier),
        parameter_candidate(identifier),
        class_candidate(identifier),
        exception_candidate(identifier),
    ]

    assert all(_invariant(candidate) for candidate in produced if candidate is not None)
