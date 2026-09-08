# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Maps vocabulary violations onto the clarity issue model.

``NonCanonicalTermIssues``. INTENT: a deprecated phrasing is a naming-clarity concern like
any other, so it rides the same ``ClarityIssue``/``Severity`` pipeline the built-in scorers use —
one issue category, ``non-canonical-term``, contributed by the glossary rather than a dictionary.
"""

from __future__ import annotations

from collections.abc import Sequence

from narrativetrace_clarity import ClarityIssue, Severity

from narrativetrace_glossary.violations import VocabularyViolation

NON_CANONICAL_TERM_CATEGORY = "non-canonical-term"
"""Clarity issue category for a phrasing the glossary has deprecated."""


def _suggestion(violation: VocabularyViolation) -> str:
    return (
        f"'{violation.alias}' is deprecated in favor of '{violation.canonical_term}' "
        f"(rename to '{violation.suggested_rename}')"
    )


def _issue_of(violation: VocabularyViolation) -> ClarityIssue:
    base = ClarityIssue(
        category=NON_CANONICAL_TERM_CATEGORY,
        element=f"{violation.site}: {violation.identifier}",
        suggestion=_suggestion(violation),
        severity=Severity.MEDIUM,
    )
    return base.with_occurrences(violation.occurrences)


def non_canonical_term_issues(
    violations: Sequence[VocabularyViolation],
) -> tuple[ClarityIssue, ...]:
    """Converts vocabulary violations into ``non-canonical-term`` clarity issues, one per violation.

    Severity is always :attr:`~narrativetrace_clarity.Severity.MEDIUM` — a deprecated phrasing is
    a real naming defect, but never as severe as ``HIGH``-tier structural issues (matches the
    plan's advisory-by-default posture: suite issues are logged, and only fail a build that opts in
    via a hard cap).
    """
    return tuple(_issue_of(violation) for violation in violations)
