# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Console summary line and violation detail formatting."""

from __future__ import annotations

import pytest
from narrativetrace_glossary import (
    TermKind,
    VocabularyViolation,
    format_violation_details,
    format_vocabulary_summary,
)

_VIOLATION = VocabularyViolation(
    context="billing",
    alias="account with overdraft",
    canonical_term="overdraft account",
    kind=TermKind.NOUN_PHRASE,
    site="OverdraftService.open",
    identifier="open_account_with_overdraft",
    occurrences=3,
    suggested_rename="open_overdraft_account",
)


def test_summary_with_no_new_terms_or_violations() -> None:
    assert (
        format_vocabulary_summary(0, [])
        == "Vocabulary: 0 new terms harvested, 0 deprecated synonyms in use"
    )


def test_summary_sums_occurrences_across_violations() -> None:
    other = VocabularyViolation(
        "billing", "other alias", "other term", TermKind.WORD, "A.a", "id", 2, "term"
    )

    summary = format_vocabulary_summary(5, [_VIOLATION, other])

    assert summary == "Vocabulary: 5 new terms harvested, 5 deprecated synonyms in use"


def test_rejects_negative_new_term_count() -> None:
    with pytest.raises(ValueError, match=r"new_term_count must not be negative: -1"):
        format_vocabulary_summary(-1, [])


def test_violation_details_empty_when_no_violations() -> None:
    assert format_violation_details([]) == ""


def test_violation_details_names_context_alias_canonical_term_and_rename() -> None:
    details = format_violation_details([_VIOLATION])

    assert "billing/account with overdraft" in details
    assert "x3" in details
    assert "overdraft account" in details
    assert "open_account_with_overdraft" in details
    assert "open_overdraft_account" in details
