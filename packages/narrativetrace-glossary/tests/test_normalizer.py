# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Behaviour of identifier normalization into glossary phrase form.

Normalized phrases are term identity in persisted glossaries, so these are lockstep rules across
all runtimes: changing one re-keys every existing ``glossary.json``.
"""

from __future__ import annotations

import re

import pytest
from narrativetrace_glossary import (
    TermCandidate,
    TermKind,
    class_candidate,
    exception_candidate,
    method_candidates,
    normalize_phrase,
    parameter_candidate,
)
from narrativetrace_glossary.normalizer import _invariant


def test_camel_pascal_and_snake_spellings_converge_to_one_phrase() -> None:
    assert normalize_phrase("accountWithOverdraft") == "account with overdraft"
    assert normalize_phrase("AccountWithOverdraft") == "account with overdraft"
    assert normalize_phrase("account_with_overdraft") == "account with overdraft"


def test_singularizes_regular_plural_nouns() -> None:
    assert normalize_phrase("overdraftAccounts") == "overdraft account"


def test_singularizes_ies_plurals_to_a_y_stem() -> None:
    assert normalize_phrase("entries") == "entry"
    assert normalize_phrase("ledgerEntries") == "ledger entry"
    # A bare "ies" has no stem in front of the suffix, so only the plural s comes off; one letter
    # of stem is enough to make it a plural.
    assert normalize_phrase("ies") == "ie"
    assert normalize_phrase("xies") == "xy"


def test_singularizes_es_plurals_of_sibilant_stems() -> None:
    assert normalize_phrase("addresses") == "address"
    assert normalize_phrase("taxBoxes") == "tax box"
    assert normalize_phrase("batches") == "batch"
    assert normalize_phrase("crashes") == "crash"
    # A bare "xes" has no stem in front of the suffix, so only the plural s comes off; one letter
    # of stem is enough to make it a plural ("axes" → "ax", the US spelling of "axe").
    assert normalize_phrase("xes") == "xe"
    assert normalize_phrase("axes") == "ax"


def test_keeps_words_whose_trailing_s_is_not_a_plural() -> None:
    assert normalize_phrase("status") == "status"
    assert normalize_phrase("analysis") == "analysis"
    assert normalize_phrase("progress") == "progress"
    # Unlisted -us words rely on the ending alone, not on the s-final singular table.
    assert normalize_phrase("consensus") == "consensus"
    assert normalize_phrase("nucleus") == "nucleus"


def test_keeps_a_lone_s_token_rather_than_erasing_it() -> None:
    assert normalize_phrase("s") == "s"
    assert normalize_phrase("sRecords") == "s record"
    # Two characters is the shortest token the plural-s rule may strip.
    assert normalize_phrase("es") == "e"


def test_singularizes_se_plurals_by_stripping_only_the_final_s() -> None:
    assert normalize_phrase("cases") == "case"
    assert normalize_phrase("responses") == "response"
    assert normalize_phrase("phases") == "phase"
    assert normalize_phrase("clauses") == "clause"
    assert normalize_phrase("purposes") == "purpose"
    assert normalize_phrase("houses") == "house"
    assert normalize_phrase("promises") == "promise"


def test_never_singularizes_function_words() -> None:
    assert normalize_phrase("markedAsDone") == "marked as done"
    assert normalize_phrase("chargeWasApplied") == "charge was applied"
    assert normalize_phrase("accountHasOverdraft") == "account has overdraft"


def test_keeps_third_person_verb_tokens_untouched() -> None:
    assert normalize_phrase("containsDuplicates") == "contains duplicate"
    assert normalize_phrase("matchesRules") == "matches rule"


def test_singularizes_es_plurals_whose_stem_keeps_its_trailing_s() -> None:
    assert normalize_phrase("gases") == "gas"
    assert normalize_phrase("aliases") == "alias"
    assert normalize_phrase("lenses") == "lens"
    assert normalize_phrase("statuses") == "status"
    assert normalize_phrase("buses") == "bus"


@pytest.mark.parametrize(
    "word",
    [
        "alias", "always", "atlas", "bias", "bonus", "bus", "campus", "canvas", "census", "chaos",
        "corpus", "focus", "gas", "lens", "locus", "news", "radius", "series", "species",
        "status", "surplus", "virus",
    ],
)  # fmt: skip
def test_keeps_s_final_singular_and_invariant_plural_words(word: str) -> None:
    assert normalize_phrase(word) == word


def test_keeps_s_final_singulars_inside_a_longer_identifier() -> None:
    assert normalize_phrase("alwaysRetry") == "always retry"
    assert normalize_phrase("cameraLens") == "camera lens"


def test_a_verb_method_yields_its_verb_phrase_and_object_noun_phrase() -> None:
    assert method_candidates("openAccountWithOverdraft") == (
        TermCandidate("open account with overdraft", TermKind.VERB_PHRASE),
        TermCandidate("account with overdraft", TermKind.NOUN_PHRASE),
    )
    assert method_candidates("chargeCards") == (
        TermCandidate("charge card", TermKind.VERB_PHRASE),
        TermCandidate("card", TermKind.WORD),
    )


def test_a_bare_verb_method_yields_only_the_verb_phrase() -> None:
    assert method_candidates("charge") == (TermCandidate("charge", TermKind.VERB_PHRASE),)


def test_the_object_phrase_drops_leading_function_words() -> None:
    assert method_candidates("checkForDuplicates") == (
        TermCandidate("check for duplicate", TermKind.VERB_PHRASE),
        TermCandidate("duplicate", TermKind.WORD),
    )


def test_the_object_phrase_drops_a_whole_run_of_leading_function_words() -> None:
    assert method_candidates("filterAsOfDate") == (
        TermCandidate("filter as of date", TermKind.VERB_PHRASE),
        TermCandidate("date", TermKind.WORD),
    )


def test_a_verb_method_whose_object_is_only_function_words_yields_one_candidate() -> None:
    assert method_candidates("checkFor") == (TermCandidate("check for", TermKind.VERB_PHRASE),)


def test_a_method_without_a_leading_verb_yields_one_noun_candidate() -> None:
    assert method_candidates("overdraftLimit") == (
        TermCandidate("overdraft limit", TermKind.NOUN_PHRASE),
    )


def test_a_single_word_method_name_yields_a_word_candidate() -> None:
    assert method_candidates("overdraft") == (TermCandidate("overdraft", TermKind.WORD),)


def test_a_parameter_candidate_strips_the_trailing_id_role_token() -> None:
    assert parameter_candidate("overdraftAccountId") == TermCandidate(
        "overdraft account", TermKind.NOUN_PHRASE
    )
    assert parameter_candidate("customerIds") == TermCandidate("customer", TermKind.WORD)
    assert parameter_candidate("overdraftAccount") == TermCandidate(
        "overdraft account", TermKind.NOUN_PHRASE
    )


def test_a_class_candidate_strips_a_recognized_role_suffix() -> None:
    assert class_candidate("OverdraftService") == TermCandidate("overdraft", TermKind.WORD)
    assert class_candidate("PaymentPlanRepository") == TermCandidate(
        "payment plan", TermKind.NOUN_PHRASE
    )
    # "item" is no role suffix, so the whole name is domain vocabulary.
    assert class_candidate("InvoiceLineItem") == TermCandidate(
        "invoice line item", TermKind.NOUN_PHRASE
    )


@pytest.mark.parametrize("class_name", ["Service", "Repository", "Manager"])
def test_a_class_that_is_only_a_role_suffix_yields_no_candidate(class_name: str) -> None:
    assert class_candidate(class_name) is None


def test_an_exception_candidate_strips_the_exception_and_error_suffixes() -> None:
    assert exception_candidate("InsufficientFundsException") == TermCandidate(
        "insufficient fund", TermKind.NOUN_PHRASE
    )
    assert exception_candidate("TimeoutError") == TermCandidate("timeout", TermKind.WORD)


@pytest.mark.parametrize("exception_type_name", ["Exception", "Error"])
def test_an_exception_named_only_for_its_suffix_yields_no_candidate(
    exception_type_name: str,
) -> None:
    assert exception_candidate(exception_type_name) is None


@pytest.mark.parametrize("parameter_name", ["id", "ids", "ID", "_id"])
def test_a_parameter_that_is_only_the_id_role_token_yields_no_candidate(
    parameter_name: str,
) -> None:
    assert parameter_candidate(parameter_name) is None


def test_a_template_candidate_is_consistent_whatever_shape_its_phrase_has() -> None:
    assert _invariant(TermCandidate("charged {amount} to {account}", TermKind.TEMPLATE))


@pytest.mark.parametrize(
    ("phrase", "kind"),
    [
        ("two words", TermKind.WORD),
        ("word", TermKind.NOUN_PHRASE),
        ("account with overdraft", TermKind.VERB_PHRASE),
        ("Mixed Case", TermKind.NOUN_PHRASE),
        (" padded", TermKind.WORD),
        ("tab\tseparated", TermKind.WORD),
        ("double  spaced", TermKind.NOUN_PHRASE),
    ],
)
def test_a_candidate_whose_kind_contradicts_its_phrase_breaks_the_invariant(
    phrase: str, kind: TermKind
) -> None:
    assert not _invariant(TermCandidate(phrase, kind))


def test_a_candidate_emptied_past_its_constructor_breaks_the_invariant() -> None:
    candidate = TermCandidate("overdraft", TermKind.WORD)

    object.__setattr__(candidate, "phrase", "")

    assert not _invariant(candidate)


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_a_term_candidate_rejects_a_blank_phrase(blank: str) -> None:
    with pytest.raises(ValueError, match=r"\Aphrase must not be blank\Z"):
        TermCandidate(blank, TermKind.WORD)


@pytest.mark.parametrize("identifier", ["my var", " x ", "open\taccount", "line\nbreak"])
def test_rejects_an_identifier_carrying_whitespace(identifier: str) -> None:
    expected = re.escape(f"identifier must not contain whitespace: {identifier!r}")

    with pytest.raises(ValueError, match=rf"\A{expected}\Z"):
        normalize_phrase(identifier)


@pytest.mark.parametrize("identifier", ["", "   ", "\t\n", "_", "___"])
def test_rejects_an_identifier_with_no_word_characters(identifier: str) -> None:
    expected = re.escape(f"identifier must contain a word character: {identifier!r}")

    with pytest.raises(ValueError, match=rf"\A{expected}\Z"):
        normalize_phrase(identifier)
