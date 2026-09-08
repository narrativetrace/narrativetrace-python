# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Value model of ``glossary.json``: contexts, terms, and their identity.

``TermKind`` / ``TermStatus`` / ``SynonymAlias`` / ``TermKey`` / ``BoundedContext`` /
``GlossaryTerm`` / ``Glossary``. Java's ``jsonName()`` methods are folded into the enum *values*, so
a label round-trips through ``TermKind(label)`` / ``kind.value`` without a lookup helper.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from types import MappingProxyType

GLOSSARY_SCHEMA_VERSION = 1
"""Schema version this runtime reads and writes; the ``schemaVersion`` of a fresh glossary."""

GLOSSARY_ABBREVIATIONS_SCHEMA_VERSION = 2
"""Schema version that introduced the root-level ``abbreviations`` section.

A glossary declaring accepted shorthand is stamped at least this high, so a reader honouring the
stamp knows the section can be there. A glossary declaring none keeps
:data:`GLOSSARY_SCHEMA_VERSION` and its bytes are unchanged by this feature ever having existed.
"""

_MIN_SCHEMA_VERSION = 1
_NO_TRANSLATIONS: Mapping[str, str] = MappingProxyType({})
_NO_ABBREVIATIONS: Mapping[str, str] = MappingProxyType({})


class TermKind(Enum):
    """Grammatical shape of a glossary term; the value is its ``glossary.json`` label."""

    WORD = "word"
    NOUN_PHRASE = "noun-phrase"
    VERB_PHRASE = "verb-phrase"
    TEMPLATE = "template"


class TermStatus(Enum):
    """Curation lifecycle of a term; the value is its ``glossary.json`` label.

    Harvesting may create ``HARVESTED`` entries but never rewrites ``CURATED`` ones, and ``STALE``
    is set only by an explicit human-invoked operation — never automatically.
    """

    HARVESTED = "harvested"
    CURATED = "curated"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class SynonymAlias:
    """A deprecated phrasing of a canonical term: "this exists in the wild; use the term instead".

    Harvesting suppresses aliases — it never re-adds them as terms — and reports their use in code
    as a vocabulary violation. The alias is stored normalized (lowercase, space-separated).
    """

    alias: str
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.alias.strip():
            raise ValueError("alias must not be blank")


@dataclass(frozen=True, slots=True)
class BoundedContext:
    """A DDD bounded context, mapped to the dotted module-path prefixes it owns.

    Contexts scope term identity: the same normalized term is a distinct concept in each context.
    Prefixes are the platform equivalent of Java packages (``acme.billing``, not
    ``com.acme.billing``) and are matched delimiter-aware, so ``acme.billing`` never claims
    ``acme.billingx``. Declaring none is valid — the ``_unassigned`` fallback context does.
    """

    name: str
    packages: Sequence[str] = ()
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("context name must not be blank")
        object.__setattr__(self, "packages", tuple(self.packages))


_NO_CONTEXTS: Mapping[str, BoundedContext] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    """One canonical term within a bounded context — the unit of ubiquitous language.

    Human-owned fields (``definition``, ``translations``, ``synonyms``, a ``CURATED`` status) are
    never overwritten by harvesting. ``first_seen`` is set once at creation and never updated, so it
    cannot break harvest idempotence; it is a calendar date, never a timestamp.

    Collections are copied on construction, so a caller mutating what it passed in cannot corrupt a
    live term.
    """

    term: str
    context: str
    kind: TermKind
    status: TermStatus
    definition: str | None = None
    translations: Mapping[str, str] = _NO_TRANSLATIONS
    synonyms: Sequence[SynonymAlias] = ()
    sources: Sequence[str] = ()
    first_seen: date = field(kw_only=True)

    def __post_init__(self) -> None:
        if not self.term.strip():
            raise ValueError("term must not be blank")
        if not self.context.strip():
            raise ValueError("context must not be blank")
        if type(self.first_seen) is not date:
            raise TypeError(f"first_seen must be a date, not {type(self.first_seen).__name__}")
        object.__setattr__(self, "translations", MappingProxyType(dict(self.translations)))
        object.__setattr__(self, "synonyms", tuple(self.synonyms))
        object.__setattr__(self, "sources", tuple(self.sources))

    def __hash__(self) -> int:
        """Hashes a term by its identity alone.

        The frozen dataclass would otherwise generate a hash over every field, which raises for
        the ``translations`` mapping — leaving a supposedly immutable value unusable in a ``set``.
        Hashing ``(context, term)`` stays consistent with ``__eq__`` (equal terms agree on both)
        and never collides in practice: a glossary rejects two terms sharing that pair.
        """
        return hash((self.context, self.term))


@dataclass(frozen=True, slots=True)
class TermKey:
    """Identity of a term: bounded context plus normalized text.

    Every term and alias lookup keys on this pair — the same text is a distinct concept per context.
    """

    context: str
    normalized: str

    @classmethod
    def of(cls, term: GlossaryTerm) -> TermKey:
        """Reads the identity of an existing term."""
        return cls(term.context, term.term)

    def __str__(self) -> str:
        return f"{self.context}/{self.normalized}"


def _term_order(term: GlossaryTerm) -> tuple[str, str]:
    """Canonical order of the glossary file: context name first, then term text."""
    return (term.context, term.term)


def _find_misfiled_context(contexts: Mapping[str, BoundedContext]) -> str | None:
    for key, context in contexts.items():
        if context.name != key:
            return f"context '{context.name}' is filed under key '{key}'"
    return None


def _find_duplicate_term_key(terms: Sequence[GlossaryTerm]) -> str | None:
    seen: set[TermKey] = set()
    for term in terms:
        key = TermKey.of(term)
        if key in seen:
            return f"duplicate term key: {key}"
        seen.add(key)
    return None


def _find_undeclared_context(
    contexts: Mapping[str, BoundedContext], terms: Sequence[GlossaryTerm]
) -> str | None:
    for term in terms:
        if term.context not in contexts:
            return f"term '{term.term}' references undeclared context '{term.context}'"
    return None


def _find_alias_collision(terms: Sequence[GlossaryTerm]) -> str | None:
    keys = {TermKey.of(term) for term in terms}
    for term in terms:
        for synonym in term.synonyms:
            if TermKey(term.context, synonym.alias) in keys:
                return (
                    f"alias '{synonym.alias}' equals a canonical term in context '{term.context}'"
                )
    return None


def _find_blank_abbreviation(abbreviations: Mapping[str, str]) -> str | None:
    for abbreviation, expansion in abbreviations.items():
        if not abbreviation.strip():
            return "abbreviation must not be blank"
        if not expansion.strip():
            return f"abbreviation '{abbreviation}' has a blank expansion"
    return None


def required_schema_version(abbreviations: Mapping[str, str]) -> int:
    """Returns the lowest ``schemaVersion`` that can describe a glossary with these abbreviations.

    The stamp follows the content: declaring shorthand needs schema 2, declaring none needs 1.
    Callers pass their own stamp separately — a higher one is kept, a lower one is raised to this.
    """
    return GLOSSARY_ABBREVIATIONS_SCHEMA_VERSION if abbreviations else GLOSSARY_SCHEMA_VERSION


def _find_violation(
    contexts: Mapping[str, BoundedContext],
    terms: Sequence[GlossaryTerm],
    abbreviations: Mapping[str, str],
) -> str | None:
    """Returns the first structural violation, or ``None`` when the glossary is consistent."""
    return (
        _find_misfiled_context(contexts)
        or _find_duplicate_term_key(terms)
        or _find_undeclared_context(contexts, terms)
        or _find_alias_collision(terms)
        or _find_blank_abbreviation(abbreviations)
    )


@dataclass(frozen=True, slots=True)
class Glossary:
    """The whole domain glossary of one repository: bounded contexts plus canonical terms.

    The in-memory form of ``glossary.json``. Structural invariants are enforced at construction, so
    an inconsistent glossary can never exist: contexts are filed under their own name, identity
    ``(context, term)`` is unique, every term's context is declared, and no deprecated alias equals
    a canonical term of the same context — an alias of *another* context is an unrelated concept
    and does not collide.

    Terms are canonicalized to ``(context, term)`` order, so two glossaries holding the same
    vocabulary are equal whatever order they were built in.

    ``abbreviations`` is the project's accepted shorthand — ``fx`` → ``foreign exchange`` — as an
    explicit human decision rather than a side effect of which tokens happen to appear in committed
    terms. It is human-owned like ``definition`` and ``translations``: harvesting never writes it.

    Unlike :class:`GlossaryTerm` a glossary is deliberately **not** hashable: it is a container
    with no identity of its own, and its context mapping cannot be hashed. Compare glossaries with
    ``==``; put terms, not glossaries, in a set.

    Divergence from Java: the misfiled-context check is new here — Java's record accepts a context
    map whose key disagrees with the context's own name.
    """

    contexts: Mapping[str, BoundedContext] = _NO_CONTEXTS
    terms: Sequence[GlossaryTerm] = ()
    abbreviations: Mapping[str, str] = _NO_ABBREVIATIONS
    schema_version: int = GLOSSARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version < _MIN_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be at least 1: {self.schema_version}")
        object.__setattr__(self, "contexts", MappingProxyType(dict(self.contexts)))
        object.__setattr__(self, "terms", tuple(sorted(self.terms, key=_term_order)))
        object.__setattr__(self, "abbreviations", MappingProxyType(dict(self.abbreviations)))
        # The stamp is raised, never lowered: it must cover the features the content uses, and a
        # file already stamped higher was stamped by a human or a newer runtime.
        object.__setattr__(
            self,
            "schema_version",
            max(self.schema_version, required_schema_version(self.abbreviations)),
        )
        violation = _find_violation(self.contexts, self.terms, self.abbreviations)
        if violation is not None:
            raise ValueError(violation)


def _invariant(glossary: Glossary) -> bool:
    """Returns whether a glossary is structurally consistent.

    Constructor guards make this true for every live instance; tests re-check the same rules at
    fixture setup and teardown to catch a mutation that bypassed construction.
    """
    return (
        glossary.schema_version >= required_schema_version(glossary.abbreviations)
        and list(glossary.terms) == sorted(glossary.terms, key=_term_order)
        and _find_violation(glossary.contexts, glossary.terms, glossary.abbreviations) is None
    )
