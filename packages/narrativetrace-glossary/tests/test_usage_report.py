# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``glossary-usage.json``: the volatile per-run harvest report."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from narrativetrace_glossary import (
    USAGE_REPORT_FILE,
    GlossaryTerm,
    HarvestCandidate,
    TermKind,
    TermStatus,
    VocabularyViolation,
    usage_report_document,
    write_usage_report,
)

_NEW_TERM = GlossaryTerm(
    "overdraft account",
    "billing",
    TermKind.NOUN_PHRASE,
    TermStatus.HARVESTED,
    sources=["OverdraftService.open"],
    first_seen=date(2026, 8, 11),
)

_VIOLATION = VocabularyViolation(
    context="billing",
    alias="account with overdraft",
    canonical_term="overdraft account",
    kind=TermKind.NOUN_PHRASE,
    site="OverdraftService.open",
    identifier="open_account_with_overdraft",
    occurrences=2,
    suggested_rename="open_overdraft_account",
)

_CANDIDATE = HarvestCandidate(
    "billing",
    "overdraft account",
    TermKind.NOUN_PHRASE,
    "OverdraftService.open",
    "overdraft_account",
)


def test_document_shape() -> None:
    document = usage_report_document(
        new_terms=[_NEW_TERM], violations=[_VIOLATION], harvested=[_CANDIDATE]
    )

    assert document == {
        "newTerms": [
            {
                "context": "billing",
                "term": "overdraft account",
                "kind": "noun-phrase",
                "sources": ["OverdraftService.open"],
            }
        ],
        "violations": [
            {
                "context": "billing",
                "alias": "account with overdraft",
                "canonicalTerm": "overdraft account",
                "kind": "noun-phrase",
                "site": "OverdraftService.open",
                "identifier": "open_account_with_overdraft",
                "occurrences": 2,
                "suggestedRename": "open_overdraft_account",
            }
        ],
        "usage": [
            {
                "context": "billing",
                "phrase": "overdraft account",
                "kind": "noun-phrase",
                "occurrences": 1,
            }
        ],
    }


def test_empty_report() -> None:
    assert usage_report_document(new_terms=[], violations=[], harvested=[]) == {
        "newTerms": [],
        "violations": [],
        "usage": [],
    }


def test_writes_the_report_file_and_returns_its_path(tmp_path: Path) -> None:
    output_dir = tmp_path / "build" / "narrativetrace"

    written = write_usage_report(output_dir, new_terms=[_NEW_TERM], violations=[], harvested=[])

    assert written == output_dir / USAGE_REPORT_FILE
    assert written.is_file()
    on_disk = json.loads(written.read_text(encoding="utf-8"))
    assert on_disk["newTerms"][0]["term"] == "overdraft account"


def test_write_creates_missing_parent_directories(tmp_path: Path) -> None:
    output_dir = tmp_path / "nested" / "dir"

    write_usage_report(output_dir, new_terms=[], violations=[], harvested=[])

    assert output_dir.is_dir()


def test_written_file_ends_with_a_trailing_newline(tmp_path: Path) -> None:
    written = write_usage_report(tmp_path, new_terms=[], violations=[], harvested=[])

    assert written.read_text(encoding="utf-8").endswith("\n")
