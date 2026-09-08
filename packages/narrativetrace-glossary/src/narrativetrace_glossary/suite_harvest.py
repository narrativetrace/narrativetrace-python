# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Orchestrates one harvest run: read, merge, write back, report.

``GlossarySuiteHarvest``. INTENT: the pytest-suite hook and the ``glossary-scan`` CLI
share this exact sequence — only how they harvest (a live trace walk vs. a static AST scan)
differs, so both call this with their own ``candidates``. Vocabulary-check issues
(``non-canonical-term``) fire only when ``glossary.json`` existed *before* this run: a project
that has not committed a glossary yet has declared no vocabulary, so there is nothing for code to
have used incorrectly — matches the plan's "the commit is the human approval" rule
(:mod:`narrativetrace_glossary.vocabulary`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from narrativetrace_clarity import ClarityIssue

from narrativetrace_glossary.alias_index import build_alias_index
from narrativetrace_glossary.clarity_issues import non_canonical_term_issues
from narrativetrace_glossary.harvester import HarvestCandidate
from narrativetrace_glossary.json_reader import read_glossary_json
from narrativetrace_glossary.json_writer import write_glossary_json
from narrativetrace_glossary.markdown import render_glossary_markdown
from narrativetrace_glossary.merger import MergeResult, merge_harvest
from narrativetrace_glossary.models import Glossary
from narrativetrace_glossary.summary_formatter import format_vocabulary_summary
from narrativetrace_glossary.usage_report import write_usage_report
from narrativetrace_glossary.violations import VocabularyViolation, aggregate_violations

GLOSSARY_JSON_FILE = "glossary.json"
GLOSSARY_MARKDOWN_FILE = "glossary.md"


@dataclass(frozen=True, slots=True)
class SuiteHarvestResult:
    """What one harvest run decided: the merge, its violations, console summary, and issues."""

    merge: MergeResult
    violations: tuple[VocabularyViolation, ...]
    summary: str
    issues: tuple[ClarityIssue, ...]


def _read_existing(glossary_dir: Path) -> tuple[Glossary, bool]:
    path = glossary_dir / GLOSSARY_JSON_FILE
    if not path.is_file():
        return Glossary(), False
    return read_glossary_json(path.read_text(encoding="utf-8")), True


def _write_glossary(glossary_dir: Path, glossary: Glossary) -> None:
    glossary_dir.mkdir(parents=True, exist_ok=True)
    (glossary_dir / GLOSSARY_JSON_FILE).write_text(write_glossary_json(glossary), encoding="utf-8")
    (glossary_dir / GLOSSARY_MARKDOWN_FILE).write_text(
        render_glossary_markdown(glossary), encoding="utf-8"
    )


def run_suite_harvest(
    candidates: Sequence[HarvestCandidate],
    *,
    glossary_dir: str | Path,
    output_dir: str | Path,
    clock: Callable[[], date] | None = None,
) -> SuiteHarvestResult:
    """Reads, merges, writes back, and reports one harvest's candidates.

    Args:
        candidates: already-harvested observations (from
            :func:`~narrativetrace_glossary.harvester.harvest_traces` or
            :func:`~narrativetrace_glossary.static_scan.scan_paths`).
        glossary_dir: directory holding (or, on a first opt-in run, to receive) the committed
            ``glossary.json`` / ``glossary.md``.
        output_dir: directory to receive the volatile ``glossary-usage.json``.
        clock: forwarded to :func:`~narrativetrace_glossary.merger.merge_harvest`.

    Returns:
        The merge result, this run's vocabulary violations (empty when no glossary was committed
        before this run), the one-line console summary, and the equivalent
        ``non-canonical-term`` clarity issues.

    Whether to call this at all is the opt-in decision (the pytest hook's ``glossary.json``-
    presence/env-override gate, or a human invoking the CLI); once called, it always writes the
    merged glossary back — a no-op rewrite when nothing changed, since
    :func:`~narrativetrace_glossary.json_writer.write_glossary_json` is a pure function of content.
    """
    glossary_dir_path = Path(glossary_dir)
    existing, existed_before = _read_existing(glossary_dir_path)
    merge = merge_harvest(existing, candidates, clock=clock)
    violations = (
        aggregate_violations(merge.suppressed_alias_uses, build_alias_index(existing))
        if existed_before
        else ()
    )
    _write_glossary(glossary_dir_path, merge.glossary)
    write_usage_report(
        output_dir, new_terms=merge.new_terms, violations=violations, harvested=candidates
    )
    summary = format_vocabulary_summary(len(merge.new_terms), violations)
    return SuiteHarvestResult(merge, violations, summary, non_canonical_term_issues(violations))
