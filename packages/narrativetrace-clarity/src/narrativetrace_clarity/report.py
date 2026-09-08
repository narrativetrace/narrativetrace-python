# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Markdown renderer for clarity results.

``ClarityReportRenderer``. The suite report lists scenarios ascending by overall score,
then emits a detail block (weighted scores + issue table) for every scenario below 0.70 that has
issues. Duplicate scenario names are preserved as separate rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from narrativetrace_clarity._numeric import two_dp

if TYPE_CHECKING:
    from collections.abc import Sequence

    from narrativetrace_clarity.models import ClarityIssue, ClarityResult

_LOW_SCORE_THRESHOLD = 0.7

_SCORE_ROWS = (
    ("Method Names", "method_name_score", 0.30),
    ("Class Names", "class_name_score", 0.20),
    ("Parameter Names", "parameter_name_score", 0.25),
    ("Structural", "structural_score", 0.15),
    ("Cohesion", "cohesion_score", 0.10),
)


def render(scenario_name: str, result: ClarityResult) -> str:
    """Renders a single-scenario clarity report."""
    parts = [f"# Clarity Report: {scenario_name}\n\n", _scores_table(result)]
    if result.issues:
        parts.append("\n## Issues\n\n")
        parts.append(_issues_table(result.issues))
    return "".join(parts).rstrip()


def render_suite_report(results: Sequence[tuple[str, ClarityResult]]) -> str:
    """Renders a suite report from an ordered list of (scenario name, result) pairs."""
    parts = ["# Clarity Suite Report\n\n", "## Scenarios\n\n"]
    parts.append("| Scenario | Score |\n|----------|-------|\n")
    ordered = sorted(results, key=lambda entry: entry[1].overall_score)
    for name, result in ordered:
        parts.append(f"| {name} | {two_dp(result.overall_score)} |\n")
    for name, result in ordered:
        if result.overall_score < _LOW_SCORE_THRESHOLD and result.issues:
            parts.append(f"\n### {name}\n\n")
            parts.append(_scores_table(result))
            parts.append("\n")
            parts.append(_issues_table(result.issues))
    return "".join(parts).rstrip()


def _scores_table(result: ClarityResult) -> str:
    rows = [
        "## Scores\n\n",
        "| Category | Score | Weight | Weighted |\n",
        "|----------|-------|--------|----------|\n",
    ]
    for label, attr, weight in _SCORE_ROWS:
        score = getattr(result, attr)
        rows.append(f"| {label} | {two_dp(score)} | {weight:.2f} | {two_dp(score * weight)} |\n")
    rows.append(f"| **Overall** | **{two_dp(result.overall_score)}** | | |\n")
    return "".join(rows)


def _issues_table(issues: list[ClarityIssue]) -> str:
    rows = [
        "| Severity | Category | Element | Suggestion |\n",
        "|----------|----------|---------|------------|\n",
    ]
    for issue in sorted(issues, key=lambda i: i.impact_score, reverse=True):
        element = (
            f"`{issue.element}` (x{issue.occurrences})"
            if issue.occurrences > 1
            else f"`{issue.element}`"
        )
        rows.append(
            f"| {issue.severity.name} | {issue.category} | {element} | {issue.suggestion} |\n"
        )
    return "".join(rows)
