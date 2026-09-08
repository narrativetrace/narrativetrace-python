# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The five clarity scorers: method, class, parameter, and cohesion.

``MethodNameScorer``, ``ClassNameScorer``, ``ParameterNameScorer``, and
``CohesionScorer`` with their exact weights and coefficients. Each is a stateless function.
"""

from __future__ import annotations

from narrativetrace_clarity import abbreviations, collocations, generic_tokens, morphology, verbs
from narrativetrace_clarity.role_suffixes import Category as RoleCategory
from narrativetrace_clarity.role_suffixes import classify as classify_role
from narrativetrace_clarity.role_suffixes import expected_verbs
from narrativetrace_clarity.tokenizer import tokenize
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

_VERB_SUFFIXES = ("ate", "ize", "ise", "ify", "en")
_UNKNOWN_ROLE_SCORE = 0.7
_BROAD_ROLE_SCORE = 0.9


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mean(values: list[float], default: float) -> float:
    return sum(values) / len(values) if values else default


# --------------------------------------------------------------------------- #
# Method names                                                                 #
# --------------------------------------------------------------------------- #
_METHOD_WEIGHTS = {
    "verb": 0.45,
    "specificity": 0.15,
    "abbreviation": 0.10,
    "count": 0.15,
    "morphology": 0.15,
}
_METHOD_SINGLE_BASE = {
    verbs.Category.GENERIC: 0.10,
    verbs.Category.BOOLEAN_PREFIX: 0.40,
    verbs.Category.STANDARD: 0.45,
    verbs.Category.DOMAIN: 0.60,
}


def score_method_name(method_name: str, vocabulary: DomainVocabulary = EMPTY) -> float:
    """Scores a method name (verb quality, specificity, morphology).

    ``vocabulary`` is the project's committed glossary vocabulary, which extends every dictionary
    consulted here without overriding any of them.
    """
    tokens = tokenize(method_name)
    if not tokens:
        return 0.0
    if len(tokens) == 1:
        return _score_method_single(tokens[0], vocabulary)
    return _score_method_multi(tokens, vocabulary)


def _score_method_single(token: str, vocabulary: DomainVocabulary) -> float:
    category, _ = verbs.categorize(token, vocabulary)
    if category in _METHOD_SINGLE_BASE:
        base = _METHOD_SINGLE_BASE[category]
    else:
        base = (
            0.55 if morphology.analyze(token, vocabulary) is morphology.PartOfSpeech.VERB else 0.50
        )
    entry = abbreviations.lookup(token, vocabulary)
    if entry is not None:
        base *= entry.score
    return _clamp(base)


def _score_method_multi(tokens: list[str], vocabulary: DomainVocabulary) -> float:
    first = tokens[0]
    return _clamp(
        _method_verb_quality(first, vocabulary) * _METHOD_WEIGHTS["verb"]
        + _method_token_specificity(tokens, vocabulary) * _METHOD_WEIGHTS["specificity"]
        + _score_abbreviations_by_score(tokens, vocabulary) * _METHOD_WEIGHTS["abbreviation"]
        + _method_token_count(len(tokens)) * _METHOD_WEIGHTS["count"]
        + _method_morphology(first, vocabulary) * _METHOD_WEIGHTS["morphology"]
    )


def _method_verb_quality(first: str, vocabulary: DomainVocabulary) -> float:
    category, score = verbs.categorize(first, vocabulary)
    if category is verbs.Category.UNKNOWN:
        return 0.6 if morphology.analyze(first, vocabulary) is morphology.PartOfSpeech.VERB else 0.4
    return score


def _method_token_specificity(tokens: list[str], vocabulary: DomainVocabulary) -> float:
    return _mean([generic_tokens.detect(t, vocabulary)[1] for t in tokens[1:]], 0.0)


def _method_token_count(count: int) -> float:
    if 2 <= count <= 4:
        return 1.0
    if count == 1:
        return 0.6
    return max(0.0, 0.7 - 0.15 * (count - 4))


def _method_morphology(first: str, vocabulary: DomainVocabulary) -> float:
    category, _ = verbs.categorize(first, vocabulary)
    in_dictionary = category is not verbs.Category.UNKNOWN
    if category is verbs.Category.GENERIC:
        return 0.3
    has_suffix = _has_verb_suffix(first)
    if in_dictionary and has_suffix:
        return 1.0
    if in_dictionary or has_suffix:
        return 0.8
    return 0.3


def _has_verb_suffix(token: str) -> bool:
    if len(token) < 4:
        return False
    return any(token.endswith(s) and len(token) > len(s) for s in _VERB_SUFFIXES)


# --------------------------------------------------------------------------- #
# Class names                                                                  #
# --------------------------------------------------------------------------- #
_CLASS_WEIGHTS = {
    "role": 0.50,
    "prefix": 0.20,
    "abbreviation": 0.10,
    "count": 0.10,
    "morphology": 0.10,
}
_PREFIX_TIER_SCORES = {
    generic_tokens.Tier.MEANINGLESS: 0.0,
    generic_tokens.Tier.VAGUE: 0.2,
    generic_tokens.Tier.TYPED_GENERIC: 0.7,
    generic_tokens.Tier.NOT_GENERIC: 1.0,
}
_CLASS_MORPH_SCORES = {
    morphology.PartOfSpeech.NOUN: 1.0,
    morphology.PartOfSpeech.ADJECTIVE: 0.9,
    morphology.PartOfSpeech.VERB: 0.3,
    morphology.PartOfSpeech.UNKNOWN: 0.7,
}


def score_class_name(class_name: str, vocabulary: DomainVocabulary = EMPTY) -> float:
    """Scores a class name (role suffix, prefix quality, morphology).

    ``vocabulary`` is the project's committed glossary vocabulary, which extends every dictionary
    consulted here without overriding any of them.
    """
    tokens = tokenize(class_name)
    if not tokens:
        return 0.0
    if len(tokens) == 1:
        return _score_class_single(tokens[0], vocabulary)
    return _score_class_multi(tokens, vocabulary)


def _score_class_single(token: str, vocabulary: DomainVocabulary) -> float:
    category, _ = classify_role(token)
    if category is RoleCategory.GENERIC:
        return 0.05
    if category in (RoleCategory.DESIGN_PATTERN, RoleCategory.FUNCTIONAL):
        return 0.10
    if morphology.analyze(token, vocabulary) is morphology.PartOfSpeech.ADJECTIVE:
        return 0.85
    return 0.75


def _score_class_multi(tokens: list[str], vocabulary: DomainVocabulary) -> float:
    last = tokens[-1]
    return _clamp(
        _class_role_suffix(last) * _CLASS_WEIGHTS["role"]
        + _class_prefix_quality(tokens[:-1], vocabulary) * _CLASS_WEIGHTS["prefix"]
        + _score_abbreviations_by_score(tokens, vocabulary) * _CLASS_WEIGHTS["abbreviation"]
        + _class_token_count(len(tokens)) * _CLASS_WEIGHTS["count"]
        + _CLASS_MORPH_SCORES[morphology.analyze(last, vocabulary)] * _CLASS_WEIGHTS["morphology"]
    )


def _class_role_suffix(last: str) -> float:
    category, _ = classify_role(last)
    if category in (RoleCategory.DESIGN_PATTERN, RoleCategory.FUNCTIONAL):
        return 1.0
    if category is RoleCategory.GENERIC:
        return 0.3
    return 0.8


def _class_prefix_quality(prefix_tokens: list[str], vocabulary: DomainVocabulary) -> float:
    return _mean(
        [_PREFIX_TIER_SCORES[generic_tokens.detect(t, vocabulary)[0]] for t in prefix_tokens], 0.0
    )


def _class_token_count(count: int) -> float:
    if 2 <= count <= 3:
        return 1.0
    if count == 1:
        return 0.5
    return max(0.0, 0.9 - 0.1 * (count - 3))


# --------------------------------------------------------------------------- #
# Parameter names                                                              #
# --------------------------------------------------------------------------- #
_PARAM_ABBR_TIER_SCORES = {
    abbreviations.Tier.UNIVERSAL: 1.0,
    abbreviations.Tier.WELL_KNOWN: 0.8,
    abbreviations.Tier.AMBIGUOUS: 0.5,
}


def score_parameter_name(param_name: str, vocabulary: DomainVocabulary = EMPTY) -> float:
    """Scores a parameter name (specificity, abbreviation, domain presence).

    ``vocabulary`` is the project's committed glossary vocabulary, which extends both dictionaries
    consulted here without overriding either.
    """
    tokens = tokenize(param_name)
    if not tokens:
        return 0.0
    if len(tokens) == 1:
        return _score_param_single(tokens[0], vocabulary)
    return _score_param_multi(tokens, vocabulary)


def _score_param_single(token: str, vocabulary: DomainVocabulary) -> float:
    tier, _ = generic_tokens.detect(token, vocabulary)
    if tier is generic_tokens.Tier.MEANINGLESS:
        return 0.0
    if tier is generic_tokens.Tier.VAGUE:
        return 0.10
    if tier is generic_tokens.Tier.TYPED_GENERIC:
        return 0.50
    return 0.40 if abbreviations.lookup(token, vocabulary) is not None else 0.80


def _score_param_multi(tokens: list[str], vocabulary: DomainVocabulary) -> float:
    tiers = [generic_tokens.detect(t, vocabulary)[0] for t in tokens]
    if any(tier is generic_tokens.Tier.MEANINGLESS for tier in tiers):
        return 0.15
    avg_generic = _mean([_param_generic_value(t, vocabulary) for t in tokens], 0.0)
    abbreviation = _score_abbreviations_by_tier(tokens, vocabulary)
    domain_bonus = 1.0 if any(t is generic_tokens.Tier.NOT_GENERIC for t in tiers) else 0.7
    return _clamp(avg_generic * 0.45 + abbreviation * 0.25 + domain_bonus * 0.30)


def _param_generic_value(token: str, vocabulary: DomainVocabulary) -> float:
    tier, score = generic_tokens.detect(token, vocabulary)
    return 0.9 if tier is generic_tokens.Tier.TYPED_GENERIC else score


def _score_abbreviations_by_tier(tokens: list[str], vocabulary: DomainVocabulary) -> float:
    def value(token: str) -> float:
        entry = abbreviations.lookup(token, vocabulary)
        return _PARAM_ABBR_TIER_SCORES[entry.tier] if entry is not None else 1.0

    return _mean([value(t) for t in tokens], 1.0)


# --------------------------------------------------------------------------- #
# Shared abbreviation scoring (method + class use the raw entry score)         #
# --------------------------------------------------------------------------- #
def _score_abbreviations_by_score(tokens: list[str], vocabulary: DomainVocabulary) -> float:
    def value(token: str) -> float:
        entry = abbreviations.lookup(token, vocabulary)
        return entry.score if entry is not None else 1.0

    return _mean([value(t) for t in tokens], 1.0)


# --------------------------------------------------------------------------- #
# Cohesion                                                                     #
# --------------------------------------------------------------------------- #
def score_cohesion_class(class_name: str, method_names: list[str]) -> float:
    """Scores how well a class's method verbs align with its role-suffix expectations."""
    tokens = tokenize(class_name)
    if not tokens:
        return _UNKNOWN_ROLE_SCORE
    last = tokens[-1]
    expected = expected_verbs(last)
    if not expected:
        category, _ = classify_role(last)
        return _UNKNOWN_ROLE_SCORE if category is RoleCategory.UNKNOWN else _BROAD_ROLE_SCORE
    if not method_names:
        return _UNKNOWN_ROLE_SCORE
    aligned = sum(1 for m in method_names if _is_aligned(m, expected))
    return aligned / len(method_names)


def score_cohesion_trace(class_methods: dict[str, list[str]]) -> float:
    """Averages :func:`score_cohesion_class` across all classes in a trace."""
    if not class_methods:
        return _UNKNOWN_ROLE_SCORE
    scores = [score_cohesion_class(cls, methods) for cls, methods in class_methods.items()]
    return _mean(scores, _UNKNOWN_ROLE_SCORE)


def _is_aligned(method_name: str, expected: tuple[str, ...]) -> bool:
    tokens = tokenize(method_name)
    if not tokens:
        return False
    first = tokens[0]
    return any(first.startswith(v) for v in expected)


# Re-exported for the collocation issue finder in the analyzer.
preferred_verbs = collocations.preferred_verbs
