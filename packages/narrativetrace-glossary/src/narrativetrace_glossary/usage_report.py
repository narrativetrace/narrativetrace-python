# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Volatile per-run harvest report: ``glossary-usage.json``.

``GlossaryUsageReport``. INTENT: build-directory output only — this file is regenerated
every run and never committed, unlike ``glossary.json``/``glossary.md``. It exists so a CI
artifact or a human can see exactly what one harvest observed without re-deriving it from logs:
which terms are new, which deprecated phrasings are still in use and where, and how often every
phrase this run touched was actually seen.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from narrativetrace_glossary.harvester import HarvestCandidate
from narrativetrace_glossary.models import GlossaryTerm
from narrativetrace_glossary.violations import VocabularyViolation

USAGE_REPORT_FILE = "glossary-usage.json"


def _new_term_entry(term: GlossaryTerm) -> dict[str, object]:
    return {
        "context": term.context,
        "term": term.term,
        "kind": term.kind.value,
        "sources": list(term.sources),
    }


def _violation_entry(violation: VocabularyViolation) -> dict[str, object]:
    return {
        "context": violation.context,
        "alias": violation.alias,
        "canonicalTerm": violation.canonical_term,
        "kind": violation.kind.value,
        "site": violation.site,
        "identifier": violation.identifier,
        "occurrences": violation.occurrences,
        "suggestedRename": violation.suggested_rename,
    }


def _usage_entry(candidate: HarvestCandidate) -> dict[str, object]:
    return {
        "context": candidate.context,
        "phrase": candidate.phrase,
        "kind": candidate.kind.value,
        "occurrences": candidate.occurrences,
    }


def usage_report_document(
    *,
    new_terms: Sequence[GlossaryTerm],
    violations: Sequence[VocabularyViolation],
    harvested: Sequence[HarvestCandidate],
) -> dict[str, object]:
    """Builds the report body as a plain dict — the pure half, kept separate for easy testing."""
    return {
        "newTerms": [_new_term_entry(term) for term in new_terms],
        "violations": [_violation_entry(violation) for violation in violations],
        "usage": [_usage_entry(candidate) for candidate in harvested],
    }


def write_usage_report(
    output_dir: str | Path,
    *,
    new_terms: Sequence[GlossaryTerm],
    violations: Sequence[VocabularyViolation],
    harvested: Sequence[HarvestCandidate],
) -> Path:
    """Writes ``glossary-usage.json`` under ``output_dir``, creating it if needed.

    Returns:
        The path written, so a caller can echo it without re-deriving the filename.
    """
    document = usage_report_document(
        new_terms=new_terms, violations=violations, harvested=harvested
    )
    path = Path(output_dir) / USAGE_REPORT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
