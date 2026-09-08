# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins dictionary sizes, overlap guards, and the primitives (tokenizer/morphology/generic)."""

from __future__ import annotations

import pytest
from narrativetrace_clarity import (
    abbreviations,
    collocations,
    generic_tokens,
    morphology,
    role_suffixes,
    verbs,
)
from narrativetrace_clarity.tokenizer import tokenize


class TestVerbDictionary:
    def test_size_floors_match_java(self) -> None:
        assert len(verbs.DOMAIN_VERBS) == 828
        assert len(verbs.STANDARD_VERBS) == 197
        assert len(verbs.GENERIC_VERBS) == 21
        assert len(verbs.BOOLEAN_PREFIXES) == 17

    def test_total_unique_verbs_is_1053(self) -> None:
        union = (
            verbs.DOMAIN_VERBS | verbs.STANDARD_VERBS | verbs.GENERIC_VERBS | verbs.BOOLEAN_PREFIXES
        )
        assert len(union) == 1053

    def test_generic_and_boolean_disjoint_from_domain(self) -> None:
        assert not (verbs.GENERIC_VERBS & verbs.DOMAIN_VERBS)
        assert not (verbs.BOOLEAN_PREFIXES & verbs.DOMAIN_VERBS)

    @pytest.mark.parametrize(
        ("verb", "category", "score"),
        [
            ("charge", verbs.Category.DOMAIN, 1.0),
            ("is", verbs.Category.BOOLEAN_PREFIX, 1.0),
            ("create", verbs.Category.STANDARD, 0.8),
            ("process", verbs.Category.GENERIC, 0.4),
            ("zzzz", verbs.Category.UNKNOWN, 0.3),
        ],
    )
    def test_categorize(self, verb: str, category: verbs.Category, score: float) -> None:
        assert verbs.categorize(verb) == (category, score)

    def test_boolean_prefix_wins_over_domain_when_ambiguous(self) -> None:
        # "is" is a boolean prefix, checked before domain — always BOOLEAN_PREFIX.
        assert verbs.categorize("IS")[0] is verbs.Category.BOOLEAN_PREFIX


class TestAbbreviations:
    def test_size_and_tiers(self) -> None:
        assert len(abbreviations._ABBREVIATIONS) == 187

    @pytest.mark.parametrize(
        ("token", "tier", "score"),
        [
            ("id", abbreviations.Tier.UNIVERSAL, 0.8),
            ("mgr", abbreviations.Tier.WELL_KNOWN, 0.6),
            ("cust", abbreviations.Tier.AMBIGUOUS, 0.3),
        ],
    )
    def test_lookup(self, token: str, tier: abbreviations.Tier, score: float) -> None:
        entry = abbreviations.lookup(token)
        assert entry is not None
        assert entry.tier is tier
        assert entry.score == score

    def test_unknown_returns_none(self) -> None:
        assert abbreviations.lookup("customer") is None


class TestRoleSuffixes:
    def test_size_floors(self) -> None:
        assert len(role_suffixes._DESIGN_PATTERN_SUFFIXES) == 15
        assert len(role_suffixes._FUNCTIONAL_SUFFIXES) == 50
        assert len(role_suffixes._GENERIC_SUFFIXES) == 13

    @pytest.mark.parametrize(
        ("suffix", "category", "score"),
        [
            ("service", role_suffixes.Category.DESIGN_PATTERN, 1.0),
            ("validator", role_suffixes.Category.FUNCTIONAL, 1.0),
            ("manager", role_suffixes.Category.GENERIC, 0.3),
            ("widget", role_suffixes.Category.UNKNOWN, 0.6),
        ],
    )
    def test_classify(self, suffix: str, category: role_suffixes.Category, score: float) -> None:
        assert role_suffixes.classify(suffix) == (category, score)

    def test_expected_verbs(self) -> None:
        assert role_suffixes.expected_verbs("repository")[:2] == ("find", "save")
        assert role_suffixes.expected_verbs("service") == ()
        assert role_suffixes.expected_verbs("widget") == ()


class TestCollocations:
    def test_preferred_verbs(self) -> None:
        assert "reconcile" in collocations.preferred_verbs("ledger")
        assert collocations.preferred_verbs("nonexistentnoun") == frozenset()
        assert collocations.preferred_verbs("") == frozenset()

    def test_is_preferred(self) -> None:
        assert collocations.is_preferred("reconcile", "ledger")
        assert not collocations.is_preferred("check", "ledger")
        assert not collocations.is_preferred("", "ledger")


class TestTokenizer:
    @pytest.mark.parametrize(
        ("identifier", "tokens"),
        [
            ("placeOrder", ["place", "order"]),
            ("OrderService", ["order", "service"]),
            ("customer_id", ["customer", "id"]),
            ("HTTPServer", ["http", "server"]),
            ("parseHTML5", ["parse", "html", "5"]),
            ("", []),
        ],
    )
    def test_tokenize(self, identifier: str, tokens: list[str]) -> None:
        assert tokenize(identifier) == tokens


class TestGenericTokens:
    @pytest.mark.parametrize(
        ("token", "tier", "score"),
        [
            ("foo", generic_tokens.Tier.MEANINGLESS, 0.0),
            ("x", generic_tokens.Tier.MEANINGLESS, 0.0),
            ("data", generic_tokens.Tier.VAGUE, 0.2),
            ("id", generic_tokens.Tier.TYPED_GENERIC, 0.5),
            ("customer", generic_tokens.Tier.NOT_GENERIC, 1.0),
        ],
    )
    def test_detect(self, token: str, tier: generic_tokens.Tier, score: float) -> None:
        assert generic_tokens.detect(token) == (tier, score)


class TestMorphology:
    @pytest.mark.parametrize(
        ("token", "pos"),
        [
            ("charge", morphology.PartOfSpeech.VERB),  # verb dictionary
            ("customize", morphology.PartOfSpeech.VERB),  # -ize suffix
            ("information", morphology.PartOfSpeech.NOUN),  # -tion
            ("comparable", morphology.PartOfSpeech.ADJECTIVE),  # -able
            ("xy", morphology.PartOfSpeech.UNKNOWN),  # too short
        ],
    )
    def test_analyze(self, token: str, pos: morphology.PartOfSpeech) -> None:
        assert morphology.analyze(token) is pos
