# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Lightweight part-of-speech guessing via the verb dictionary plus suffix heuristics.

``MorphologyAnalyzer``. The verb dictionary takes precedence; otherwise suffixes are
checked in priority order verb > noun > adjective. Tokens shorter than four chars are UNKNOWN.
"""

from __future__ import annotations

from enum import Enum

from narrativetrace_clarity import verbs
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

_MIN_SUFFIX_LENGTH = 4

_VERB_SUFFIXES = ("ate", "ize", "ise", "ify", "en")
_NOUN_SUFFIXES = (
    "tion",
    "sion",
    "ment",
    "ness",
    "ity",
    "ance",
    "ence",
    "er",
    "or",
    "ary",
    "ery",
    "ory",
)
_ADJECTIVE_SUFFIXES = ("able", "ible", "ive", "ous", "al", "ic", "ed")


class PartOfSpeech(Enum):
    """Coarse part-of-speech buckets."""

    VERB = "VERB"
    NOUN = "NOUN"
    ADJECTIVE = "ADJECTIVE"
    UNKNOWN = "UNKNOWN"


def analyze(token: str, vocabulary: DomainVocabulary = EMPTY) -> PartOfSpeech:
    """Returns the guessed part of speech for a single token.

    Verb detection defers to the verb dictionary, so a project's declared verbs read as verbs here
    too — ``fold`` is a verb in a project whose glossary says so.
    """
    lower = token.lower()
    category, _ = verbs.categorize(lower, vocabulary)
    if category is not verbs.Category.UNKNOWN:
        return PartOfSpeech.VERB
    if len(lower) < _MIN_SUFFIX_LENGTH:
        return PartOfSpeech.UNKNOWN
    if _matches_suffix(lower, _VERB_SUFFIXES):
        return PartOfSpeech.VERB
    if _matches_suffix(lower, _NOUN_SUFFIXES):
        return PartOfSpeech.NOUN
    if _matches_suffix(lower, _ADJECTIVE_SUFFIXES):
        return PartOfSpeech.ADJECTIVE
    return PartOfSpeech.UNKNOWN


def _matches_suffix(word: str, suffixes: tuple[str, ...]) -> bool:
    return any(word.endswith(suffix) and len(word) > len(suffix) for suffix in suffixes)
