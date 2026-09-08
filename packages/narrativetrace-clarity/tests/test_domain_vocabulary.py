# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The project's own vocabulary: what a committed glossary teaches, and what it cannot override."""

from __future__ import annotations

import pytest
from narrativetrace_clarity import abbreviations, generic_tokens, verbs
from narrativetrace_clarity.analyzer import analyze
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree


class TestDomainVocabulary:
    def test_empty_vocabulary_knows_nothing(self) -> None:
        assert EMPTY.is_empty()
        assert not EMPTY.is_domain_verb("fold")
        assert not EMPTY.is_domain_noun("tranche")
        assert not EMPTY.is_accepted_abbreviation("fx")

    def test_recognizes_declared_verbs_and_nouns_and_keeps_them_apart(self) -> None:
        vocabulary = DomainVocabulary.of(["fold"], ["tranche"])

        assert vocabulary.is_domain_verb("fold")
        assert vocabulary.is_domain_noun("tranche")
        assert not vocabulary.is_domain_verb("tranche")
        assert not vocabulary.is_domain_noun("fold")

    def test_any_populated_set_makes_the_vocabulary_non_empty(self) -> None:
        assert not DomainVocabulary.of(["fold"], []).is_empty()
        assert not DomainVocabulary.of([], ["tranche"]).is_empty()
        assert not DomainVocabulary.of([], [], ["fx"]).is_empty()
        assert DomainVocabulary.of(["credit tranche"], [" "], [""]).is_empty()

    def test_only_the_abbreviations_section_declares_accepted_shorthand(self) -> None:
        vocabulary = DomainVocabulary.of(["calc"], ["fx"], ["acc"])

        assert vocabulary.is_accepted_abbreviation("acc")
        assert not vocabulary.is_accepted_abbreviation("calc")
        assert not vocabulary.is_accepted_abbreviation("fx")
        assert not vocabulary.is_accepted_abbreviation("mgr")

    def test_matches_regardless_of_case(self) -> None:
        vocabulary = DomainVocabulary.of(["Fold"], ["Tranche"], ["FX"])

        assert vocabulary.is_domain_verb("FOLD")
        assert vocabulary.is_domain_noun("tranche")
        assert vocabulary.is_accepted_abbreviation("fx")

    def test_drops_blank_and_multi_word_entries(self) -> None:
        vocabulary = DomainVocabulary.of(["fold ", " "], ["credit tranche", ""], ["fx ", "f x"])

        assert vocabulary.is_domain_verb("fold")
        assert not vocabulary.is_domain_noun("credit tranche")
        assert not vocabulary.is_domain_noun("credit")
        assert vocabulary.is_accepted_abbreviation("fx")
        assert not vocabulary.is_accepted_abbreviation("f x")
        assert not vocabulary.is_accepted_abbreviation("")

    def test_is_value_based_regardless_of_input_order_or_case(self) -> None:
        assert DomainVocabulary.of(
            ["fold", "Settle"], ["tranche"], ["fx", "ACC"]
        ) == DomainVocabulary.of(["SETTLE", "fold"], ["Tranche"], ["acc", "FX"])

    def test_an_omitted_abbreviations_argument_declares_no_shorthand(self) -> None:
        assert not DomainVocabulary.of(["fold"], ["fx"]).is_accepted_abbreviation("fx")


class TestBuiltInDictionariesKeepTheirAuthority:
    def test_a_declared_verb_the_dictionaries_do_not_know_becomes_domain(self) -> None:
        assert verbs.categorize("fold")[0] is verbs.Category.UNKNOWN
        assert verbs.categorize("fold", DomainVocabulary.of(["fold"], []))[0] is (
            verbs.Category.DOMAIN
        )

    def test_a_declared_verb_outranks_the_standard_tier(self) -> None:
        assert verbs.categorize("send")[0] is verbs.Category.STANDARD
        assert verbs.categorize("send", DomainVocabulary.of(["send"], []))[0] is (
            verbs.Category.DOMAIN
        )

    @pytest.mark.parametrize("verb", ["process", "handle"])
    def test_generic_verbs_stay_generic_however_a_project_declares_them(self, verb: str) -> None:
        vocabulary = DomainVocabulary.of(["process", "handle"], [])

        assert verbs.categorize(verb, vocabulary)[0] is verbs.Category.GENERIC

    def test_boolean_prefixes_stay_boolean_however_a_project_declares_them(self) -> None:
        assert verbs.categorize("is", DomainVocabulary.of(["is"], []))[0] is (
            verbs.Category.BOOLEAN_PREFIX
        )

    def test_declared_nouns_are_not_verbs(self) -> None:
        assert verbs.categorize("tranche", DomainVocabulary.of([], ["tranche"]))[0] is (
            verbs.Category.UNKNOWN
        )

    def test_generic_and_standard_verbs_are_disjoint(self) -> None:
        # Load-bearing: categorize decides generic before the project's verbs, which puts generic
        # ahead of standard. That reordering is behaviour-preserving only while these are disjoint.
        assert not (verbs.GENERIC_VERBS & verbs.STANDARD_VERBS)

    @pytest.mark.parametrize("token", ["position", "record"])
    def test_a_declared_noun_lifts_a_broad_or_vague_word_to_domain(self, token: str) -> None:
        vocabulary = DomainVocabulary.of([], ["position", "record"])

        assert generic_tokens.detect(token, vocabulary)[0] is generic_tokens.Tier.NOT_GENERIC

    @pytest.mark.parametrize("token", ["temp", "foo", "x"])
    def test_meaningless_placeholders_are_not_rescued_by_being_written_down(
        self, token: str
    ) -> None:
        vocabulary = DomainVocabulary.of([], ["temp", "foo", "x"])

        assert generic_tokens.detect(token, vocabulary)[0] is generic_tokens.Tier.MEANINGLESS

    def test_declared_verbs_are_not_nouns(self) -> None:
        vocabulary = DomainVocabulary.of(["data"], [])

        assert generic_tokens.detect("data", vocabulary)[0] is generic_tokens.Tier.VAGUE

    def test_accepted_shorthand_stops_being_an_abbreviation(self) -> None:
        vocabulary = DomainVocabulary.of([], [], ["acc", "calc"])

        assert abbreviations.lookup("acc") is not None
        assert abbreviations.lookup("acc", vocabulary) is None
        assert abbreviations.lookup("calc", vocabulary) is None

    def test_a_phrase_token_does_not_accept_shorthand_the_project_never_declared(self) -> None:
        """Committing `calc total` must not silently drop the `calc` spell-out repository-wide."""
        vocabulary = DomainVocabulary.of([], ["calc", "total"])

        entry = abbreviations.lookup("calc", vocabulary)

        assert entry is not None
        assert entry.expansion == "calculate or calculation"

    def test_undeclared_abbreviations_stay_penalized(self) -> None:
        entry = abbreviations.lookup("mgr", DomainVocabulary.of([], [], ["acc"]))

        assert entry is not None
        assert entry.tier is abbreviations.Tier.WELL_KNOWN


def _tree(method_name: str, *param_names: str) -> TraceTree:
    signature = MethodSignature(
        "TrancheService",
        method_name,
        [ParameterCapture(name, '"x"') for name in param_names],
    )
    return TraceTree([TraceNode(signature, [], Returned('"x"'), 1_000_000)])


class TestAnalyzeWithAProjectVocabulary:
    def test_raises_the_score_of_the_projects_own_words(self) -> None:
        tree = _tree("foldTranche", "tranche")
        vocabulary = DomainVocabulary.of(["fold"], ["tranche"])

        without_glossary = analyze(tree)
        with_glossary = analyze(tree, vocabulary)

        assert with_glossary.method_name_score > without_glossary.method_name_score
        assert with_glossary.overall_score > without_glossary.overall_score

    def test_an_omitted_vocabulary_scores_exactly_as_an_empty_one(self) -> None:
        tree = _tree("calculateTotal", "orderAmount")

        assert analyze(tree, EMPTY) == analyze(tree)

    def test_declaring_a_generic_verb_changes_no_score(self) -> None:
        tree = _tree("processTranche", "tranche")
        nouns_only = DomainVocabulary.of([], ["tranche"])
        with_generic_verb = DomainVocabulary.of(["process"], ["tranche"])

        assert analyze(tree, with_generic_verb) == analyze(tree, nouns_only)

    def test_declaring_an_unknown_verb_does_change_the_score(self) -> None:
        tree = _tree("foldTranche", "tranche")
        nouns_only = DomainVocabulary.of([], ["tranche"])
        with_verb = DomainVocabulary.of(["fold"], ["tranche"])

        assert analyze(tree, with_verb).method_name_score > (
            analyze(tree, nouns_only).method_name_score
        )
