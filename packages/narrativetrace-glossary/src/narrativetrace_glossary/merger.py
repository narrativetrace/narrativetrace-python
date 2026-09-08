# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Additive merge of harvested candidates into an existing glossary.

``GlossaryMerger`` / ``MergeResult``. INTENT: the merge rules of ADR-012, enforced
structurally — existing entries are never removed or mutated (human-authored fields are
sacrosanct), unseen ``(context, phrase)`` pairs join as ``harvested`` terms, phrases matching a
deprecated alias are suppressed and reported, and re-merging the same harvest is a no-op.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from narrativetrace_glossary.alias_index import build_alias_index
from narrativetrace_glossary.context_resolver import UNASSIGNED_CONTEXT
from narrativetrace_glossary.harvester import HarvestCandidate
from narrativetrace_glossary.models import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    TermKey,
    TermKind,
    TermStatus,
)

_SOURCE_LIMIT = 3
"""How many observed sites a new term records — enough to locate it, few enough to stay stable."""

_UNASSIGNED_DESCRIPTION = "Harvested terms not yet mapped to a context"


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Outcome of one additive merge: the merged glossary plus what this merge decided.

    The single value all run output derives from — the glossary is written back to disk,
    ``new_terms`` feeds the console summary, and ``suppressed_alias_uses`` feeds vocabulary-
    violation reporting.
    """

    glossary: Glossary
    new_terms: Sequence[GlossaryTerm] = ()
    suppressed_alias_uses: Sequence[HarvestCandidate] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "new_terms", tuple(self.new_terms))
        object.__setattr__(self, "suppressed_alias_uses", tuple(self.suppressed_alias_uses))


def merge_harvest(
    existing: Glossary,
    candidates: Sequence[HarvestCandidate],
    *,
    clock: Callable[[], date] | None = None,
) -> MergeResult:
    """Merges harvested observations into the glossary, additively.

    Args:
        existing: glossary to merge into; never mutated.
        candidates: observations of one run, as returned by
            :func:`~narrativetrace_glossary.harvester.harvest_traces`.
        clock: supplies the ``first_seen`` date stamped on newly created terms. Defaults to
            today in UTC; inject a fixed clock to make a merge reproducible under test.

    Returns:
        The merged glossary plus the terms this merge added and the alias uses it suppressed.

    Raises:
        TypeError: if ``existing`` is not a :class:`Glossary` or ``clock`` is not callable.
    """
    if not isinstance(existing, Glossary):
        raise TypeError("existing must be a Glossary")
    if clock is not None and not callable(clock):
        raise TypeError("clock must be callable")
    suppressed: list[HarvestCandidate] = []
    accumulators = _classify_unseen(existing, candidates, suppressed)
    first_seen = clock() if clock is not None else datetime.now(UTC).date()
    new_terms = [
        _new_term(key, kind, sites, first_seen) for key, (kind, sites) in accumulators.items()
    ]
    result = MergeResult(_merged(existing, new_terms), new_terms, suppressed)
    assert _invariant(result, existing), "a merge must be additive and must add only what is new"
    return result


def _invariant(result: MergeResult, existing: Glossary) -> bool:
    """Returns whether a merge result is consistent with the glossary it merged into.

    The additive contract of ADR-012, restated as a check: nothing the caller already had was
    dropped or rewritten, the human-owned abbreviations section came through unchanged, every
    reported new term is really in the merged glossary and really is new, and no observation was
    both suppressed and added.
    """
    merged = result.glossary
    added = {TermKey.of(term) for term in result.new_terms}
    return (
        set(existing.terms) <= set(merged.terms)
        and dict(existing.contexts).items() <= dict(merged.contexts).items()
        and dict(merged.abbreviations) == dict(existing.abbreviations)
        and merged.schema_version == existing.schema_version
        and set(result.new_terms) <= set(merged.terms)
        and added.isdisjoint(TermKey.of(term) for term in existing.terms)
        and added.isdisjoint(
            TermKey(use.context, use.phrase) for use in result.suppressed_alias_uses
        )
    )


def _classify_unseen(
    existing: Glossary,
    candidates: Sequence[HarvestCandidate],
    suppressed: list[HarvestCandidate],
) -> dict[TermKey, tuple[TermKind, list[str]]]:
    """Sorts observations into suppressed alias uses and accumulators for genuinely new terms."""
    aliases = build_alias_index(existing)
    known = {TermKey.of(term) for term in existing.terms}
    accumulators: dict[TermKey, tuple[TermKind, list[str]]] = {}
    for candidate in candidates:
        key = TermKey(candidate.context, candidate.phrase)
        if key in aliases:
            suppressed.append(candidate)
        elif key not in known:
            _, sites = accumulators.setdefault(key, (candidate.kind, []))
            if candidate.site not in sites and len(sites) < _SOURCE_LIMIT:
                sites.append(candidate.site)
    return accumulators


def _new_term(key: TermKey, kind: TermKind, sites: Sequence[str], first_seen: date) -> GlossaryTerm:
    return GlossaryTerm(
        key.normalized,
        key.context,
        kind,
        TermStatus.HARVESTED,
        sources=sites,
        first_seen=first_seen,
    )


def _merged(existing: Glossary, new_terms: Sequence[GlossaryTerm]) -> Glossary:
    contexts = dict(existing.contexts)
    for term in new_terms:
        if term.context not in contexts:
            contexts[term.context] = _declared_context(term.context)
    terms = [*existing.terms, *new_terms]
    # Abbreviations are human-owned: a harvest carries the section through untouched, never adding
    # to it. Accepted shorthand is a decision, and a run is not one.
    return Glossary(contexts, terms, existing.abbreviations, existing.schema_version)


def _declared_context(name: str) -> BoundedContext:
    """Declares a context a harvest referenced but the file did not, so the glossary stays whole."""
    description = _UNASSIGNED_DESCRIPTION if name == UNASSIGNED_CONTEXT else None
    return BoundedContext(name, (), description)
