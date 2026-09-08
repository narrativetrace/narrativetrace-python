# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Mapping vocabulary violations onto ``non-canonical-term`` clarity issues."""

from __future__ import annotations

from narrativetrace_clarity import Severity
from narrativetrace_glossary import (
    NON_CANONICAL_TERM_CATEGORY,
    TermKind,
    VocabularyViolation,
    non_canonical_term_issues,
)


def _violation(occurrences: int = 1) -> VocabularyViolation:
    return VocabularyViolation(
        context="billing",
        alias="account with overdraft",
        canonical_term="overdraft account",
        kind=TermKind.NOUN_PHRASE,
        site="OverdraftService.open",
        identifier="open_account_with_overdraft",
        occurrences=occurrences,
        suggested_rename="open_overdraft_account",
    )


def test_maps_a_violation_to_a_medium_severity_non_canonical_term_issue() -> None:
    (issue,) = non_canonical_term_issues([_violation()])

    assert issue.category == NON_CANONICAL_TERM_CATEGORY == "non-canonical-term"
    assert issue.severity is Severity.MEDIUM
    assert issue.element == "OverdraftService.open: open_account_with_overdraft"
    assert "account with overdraft" in issue.suggestion
    assert "overdraft account" in issue.suggestion
    assert "open_overdraft_account" in issue.suggestion


def test_scales_impact_score_with_occurrences() -> None:
    (issue,) = non_canonical_term_issues([_violation(occurrences=4)])

    assert issue.occurrences == 4
    assert issue.impact_score == Severity.MEDIUM.weight * 4


def test_empty_input_yields_no_issues() -> None:
    assert non_canonical_term_issues([]) == ()


def test_one_issue_per_violation_preserving_order() -> None:
    first = _violation()
    second = VocabularyViolation(
        context="billing",
        alias="other alias",
        canonical_term="other term",
        kind=TermKind.WORD,
        site="A.a",
        identifier="id",
        occurrences=1,
        suggested_rename="term",
    )

    issues = non_canonical_term_issues([first, second])

    assert len(issues) == 2
    assert issues[0].element != issues[1].element
