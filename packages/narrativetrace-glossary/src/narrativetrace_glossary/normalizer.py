# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Normalizes code identifiers into glossary phrase form.

``TermNormalizer`` (its instance methods become module functions, as elsewhere in this
distribution). INTENT: every identifier spelling of one concept converges to a single normalized
phrase — ``accountWithOverdraft``, ``AccountWithOverdraft``, and ``account_with_overdraft`` all
become ``"account with overdraft"`` — because term and alias matching always happens on the
normalized form. Reuses the clarity distribution's identifier tokenizer (camelCase / snake_case
splitting) and morphology analyzer (verb detection); singularization is a deliberately small
English heuristic, applied to non-verb, non-stopword tokens.

Because normalized phrases are term identity in persisted glossaries, singularization must never
coin non-words from real ones (``alias`` must not become ``alia``) and must be idempotent — every
emitted token is a fixpoint of the singularizer, so re-normalizing a phrase is the identity
(property-tested). Changing these rules re-keys existing glossaries and must stay in lockstep
across all runtimes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from narrativetrace_clarity import morphology, role_suffixes, tokenizer

from narrativetrace_glossary.models import TermKind

_STOPWORDS = frozenset(
    {
        "with", "and", "or", "of", "to", "for", "by", "from", "in", "on", "at", "as", "was", "is",
        "has",
    }
)  # fmt: skip
"""Function words that must survive normalization untouched (never singularized)."""

_EXCEPTION_SUFFIXES = frozenset({"exception", "error"})
"""Exception-type suffixes stripped when harvesting failure vocabulary."""

_ES_PLURAL_ENDINGS = ("ses", "xes", "zes", "ches", "shes")
"""Trailing patterns whose ``es`` suffix marks a plural (``boxes``, ``classes``)."""

_S_FINAL_SINGULARS = frozenset(
    {
        "alias", "always", "atlas", "bias", "bonus", "bus", "campus", "canvas", "census", "chaos",
        "corpus", "focus", "gas", "lens", "locus", "news", "radius", "series", "species",
        "status", "surplus", "virus",
    }
)  # fmt: skip
"""Words ending in ``s`` that are singular (``alias``, Latin ``-us`` nouns), invariant plurals
(``series``), or not nouns at all (``always``) — never stripped. Also the only way an ``s``-final
``-es`` stem is accepted (``gases`` → ``gas``); an unlisted ``s``-final stem means the plural was
built as ``-se + s`` (``clauses`` → ``clause``)."""


@dataclass(frozen=True, slots=True)
class TermCandidate:
    """One harvestable phrase produced by normalization, with the shape its structure implies.

    ``TermNormalizer.Candidate``. The phrase is already normalized, so it can be used
    as term identity directly.
    """

    phrase: str
    kind: TermKind

    def __post_init__(self) -> None:
        if not self.phrase.strip():
            raise ValueError("phrase must not be blank")


def normalize_phrase(identifier: str) -> str:
    """Normalizes one identifier to phrase form: lowercase, space-separated, nouns singularized.

    Raises ``ValueError`` for an identifier normalization would erase.
    """
    phrase = " ".join(_normalized_tokens(identifier))
    assert phrase.strip(), "normalization must never erase the identifier"
    assert phrase == phrase.lower(), "a normalized phrase must be lowercase"
    return phrase


def method_candidates(method_name: str) -> tuple[TermCandidate, ...]:
    """Normalizes a method name into the harvest candidates it contributes.

    A method with a leading verb yields its verb phrase plus the object noun phrase (leading
    function words dropped); any other method yields a single noun candidate. Never returns an
    empty tuple. Raises ``ValueError`` for an identifier normalization would erase.
    """
    tokens = _normalized_tokens(method_name)
    candidates = (
        _verb_phrase_candidates(tokens) if _is_verb(tokens[0]) else (_noun_candidate(tokens),)
    )
    assert candidates, "a method always yields at least one candidate"
    assert all(_invariant(candidate) for candidate in candidates), "candidate kinds must fit"
    return candidates


def _verb_phrase_candidates(tokens: list[str]) -> tuple[TermCandidate, ...]:
    """Splits verb-led tokens into the whole verb phrase plus the object it acts on."""
    verb_phrase = TermCandidate(" ".join(tokens), TermKind.VERB_PHRASE)
    object_tokens = _without_leading_stopwords(tokens[1:])
    if not object_tokens:
        return (verb_phrase,)
    return (verb_phrase, _noun_candidate(object_tokens))


def parameter_candidate(parameter_name: str) -> TermCandidate | None:
    """Normalizes a parameter name into a noun candidate, stripping the trailing ``id`` role token.

    ``overdraftAccountId`` → ``"overdraft account"``. Returns ``None`` when only the role token
    remains (``id``) — a parameter naming no domain concept contributes no vocabulary. Raises
    ``ValueError`` for an identifier normalization would erase.
    """
    return _stripped_candidate(parameter_name, lambda token: token == "id")


def class_candidate(class_name: str) -> TermCandidate | None:
    """Normalizes a class name into a noun candidate, stripping a recognized role suffix.

    ``OverdraftService`` → ``"overdraft"``. Returns ``None`` when only the role suffix remains
    (``Service``). Raises ``ValueError`` for an identifier normalization would erase.
    """
    return _stripped_candidate(class_name, _is_role_suffix)


def exception_candidate(exception_type_name: str) -> TermCandidate | None:
    """Normalizes an exception type name into a noun candidate, stripping its failure-role suffix.

    ``InsufficientFundsException`` → ``"insufficient fund"``, ``TimeoutError`` → ``"timeout"``.
    Returns ``None`` when only the suffix remains. Raises ``ValueError`` for an identifier
    normalization would erase.
    """
    return _stripped_candidate(exception_type_name, _EXCEPTION_SUFFIXES.__contains__)


def _is_role_suffix(token: str) -> bool:
    category, _ = role_suffixes.classify(token)
    return category is not role_suffixes.Category.UNKNOWN


def _stripped_candidate(
    identifier: str, is_trailing_role: Callable[[str], bool]
) -> TermCandidate | None:
    """Normalizes to a noun candidate minus a trailing role token, or ``None`` if none is left."""
    tokens = _normalized_tokens(identifier)
    if is_trailing_role(tokens[-1]):
        tokens = tokens[:-1]
    candidate = _noun_candidate(tokens) if tokens else None
    assert candidate is None or _invariant(candidate), "candidate kinds must fit"
    return candidate


def _normalized_tokens(identifier: str) -> list[str]:
    return [_normalize_token(token) for token in _word_tokens(identifier)]


def _word_tokens(identifier: str) -> list[str]:
    """Tokenizes, rejecting anything that is not a single code identifier.

    Two guards Java's normalizer lacks, both keeping normalized phrases canonical — they are term
    identity, so a stray space or an empty phrase corrupts a glossary key:

    - An identifier with no word character (``_``) tokenizes to nothing. Java only rejects blank
      text and then *asserts* that normalization produced something, so this either trips an
      assertion or silently yields an empty phrase.
    - Whitespace never occurs inside a code identifier, and the tokenizer does not split on it, so
      ``"my var"`` would pass through as one unsingularized token. Java relies on its harvester
      filtering non-identifiers before the normalizer sees them; here the normalizer is public API
      and rejects them itself.
    """
    tokens = tokenizer.tokenize(identifier)
    if not any(token.strip() for token in tokens):
        raise ValueError(f"identifier must contain a word character: {identifier!r}")
    if any(character.isspace() for character in identifier):
        raise ValueError(f"identifier must not contain whitespace: {identifier!r}")
    return tokens


def _normalize_token(token: str) -> str:
    """Singularizes a noun token; verbs pass through, so ``matches`` never becomes ``match``."""
    if token in _STOPWORDS or _is_verb(token):
        return token
    return _singularize(token)


def _is_verb(token: str) -> bool:
    return morphology.analyze(token) is morphology.PartOfSpeech.VERB


def _without_leading_stopwords(tokens: list[str]) -> list[str]:
    """Drops the function words a verb's object opens with (``for`` in ``check for duplicates``)."""
    start = 0
    while start < len(tokens) and tokens[start] in _STOPWORDS:
        start += 1
    return tokens[start:]


def _noun_candidate(tokens: list[str]) -> TermCandidate:
    """A single token is a word; several are a noun phrase."""
    kind = TermKind.WORD if len(tokens) == 1 else TermKind.NOUN_PHRASE
    return TermCandidate(" ".join(tokens), kind)


def _singularize(token: str) -> str:
    """Reduces a plural noun to its singular; every result is a fixpoint of this function."""
    if token in _S_FINAL_SINGULARS:
        return token
    if token.endswith("ies") and len(token) > 3:
        return f"{token[:-3]}y"
    if token.endswith(_ES_PLURAL_ENDINGS) and len(token) > 3:
        stem = token[:-2]
        if _is_stable_singular(stem):
            return stem
        # An unstable "ses" stem means the plural was built as -se + s ("cases", "responses"):
        # fall through to the single-s rule so the e survives.
    if token.endswith("s") and len(token) > 1 and not _keeps_trailing_s(token):
        return token[:-1]
    return token


def _is_stable_singular(stem: str) -> bool:
    """Returns whether :func:`_singularize` would leave this stem unchanged.

    Unlike :func:`_keeps_trailing_s`, a ``us``/``is`` ending does not bless a stem: those endings
    usually mean the plural was ``-se + s`` (``clauses`` → ``claus``, ``promises`` → ``promis``),
    so only ``ss`` stems and listed words qualify.
    """
    return not stem.endswith("s") or stem.endswith("ss") or stem in _S_FINAL_SINGULARS


def _keeps_trailing_s(token: str) -> bool:
    """Words ending in ss/us/is are not English plurals (``status``, ``analysis``)."""
    return token.endswith(("ss", "us", "is"))


def _invariant(candidate: TermCandidate) -> bool:
    """Returns whether a candidate's kind agrees with the structure of its phrase.

    The constructor cannot check this — ``kind`` is caller-supplied — so every producer asserts it
    on exit and the property suite re-checks it for arbitrary identifiers. A phrase must also be
    canonical: lowercase, single-space separated, no padding, since it *is* term identity.
    ``TEMPLATE`` carries no structural rule beyond that — a narration template is prose, harvested
    statically rather than normalized.
    """
    phrase = candidate.phrase
    if not phrase or phrase != phrase.lower() or phrase != " ".join(phrase.split()):
        return False
    tokens = phrase.split()
    if candidate.kind is TermKind.WORD:
        return len(tokens) == 1
    if candidate.kind is TermKind.NOUN_PHRASE:
        return len(tokens) > 1
    if candidate.kind is TermKind.VERB_PHRASE:
        return _is_verb(tokens[0])
    return True
