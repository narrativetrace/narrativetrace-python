# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Vocabulary violations: deprecated phrasings a harvest found still in use.

``VocabularyViolation``. INTENT: :func:`~narrativetrace_glossary.merger.merge_harvest`
already tells a caller which observations were suppressed as alias hits
(``MergeResult.suppressed_alias_uses``); this turns each one into a reportable violation carrying
the canonical replacement and a mechanical rename suggestion, so both the console summary and the
``non-canonical-term`` clarity issues have one shared source of truth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from narrativetrace_glossary.harvester import HarvestCandidate
from narrativetrace_glossary.models import GlossaryTerm, TermKey, TermKind
from narrativetrace_glossary.rename_suggester import suggest_rename


@dataclass(frozen=True, slots=True)
class VocabularyViolation:
    """One code site using a deprecated phrasing instead of its glossary-declared canonical term."""

    context: str
    alias: str
    canonical_term: str
    kind: TermKind
    site: str
    identifier: str
    occurrences: int
    suggested_rename: str

    def __post_init__(self) -> None:
        for name in ("context", "alias", "canonical_term", "site", "identifier"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be blank")
        if self.occurrences < 1:
            raise ValueError(f"occurrences must be at least 1: {self.occurrences}")


def _order(violation: VocabularyViolation) -> tuple[str, str, str, str]:
    return (violation.context, violation.alias, violation.site, violation.identifier)


def _violation_of(candidate: HarvestCandidate, canonical: GlossaryTerm) -> VocabularyViolation:
    return VocabularyViolation(
        context=candidate.context,
        alias=candidate.phrase,
        canonical_term=canonical.term,
        kind=candidate.kind,
        site=candidate.site,
        identifier=candidate.identifier,
        occurrences=candidate.occurrences,
        suggested_rename=suggest_rename(candidate.identifier, canonical.term),
    )


def aggregate_violations(
    suppressed: Sequence[HarvestCandidate], aliases: Mapping[TermKey, GlossaryTerm]
) -> tuple[VocabularyViolation, ...]:
    """Turns suppressed alias observations into reportable violations, deterministically ordered.

    Args:
        suppressed: ``MergeResult.suppressed_alias_uses`` from the merge that classified these
            observations as deprecated-alias hits against ``aliases``' glossary.
        aliases: the alias index of the glossary the merge ran against (typically
            :func:`~narrativetrace_glossary.alias_index.build_alias_index` on the same
            ``existing`` glossary passed to :func:`~narrativetrace_glossary.merger.merge_harvest`).

    Returns:
        One violation per suppressed observation, ordered by ``(context, alias, site,
        identifier)``.

    Raises:
        KeyError: if a suppressed candidate's ``(context, phrase)`` is not in ``aliases`` — a
            caller passed an alias index built against a different glossary than the merge used.
    """
    violations = [
        _violation_of(candidate, aliases[TermKey(candidate.context, candidate.phrase)])
        for candidate in suppressed
    ]
    return tuple(sorted(violations, key=_order))
