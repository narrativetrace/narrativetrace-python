# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins JSON export byte-format and Markdown suite report structure to Java."""

from __future__ import annotations

from narrativetrace_clarity import export, render, render_suite_report
from narrativetrace_clarity.models import ClarityIssue, ClarityResult, Severity


def _result(overall: float = 0.85, issues: list[ClarityIssue] | None = None) -> ClarityResult:
    return ClarityResult(overall, 0.90, 0.80, 0.85, 1.0, 0.70, issues or [])


class TestJsonExport:
    def test_empty_is_exact(self) -> None:
        assert export([]) == '{"version":"1.0","scenarios":[]}'

    def test_scenario_scores_are_two_dp(self) -> None:
        json = export([("Scenario", _result())])
        assert '"overallScore":0.85' in json
        assert '"methodNameScore":0.90' in json
        assert '"cohesionScore":0.70' in json

    def test_issue_fields(self) -> None:
        issue = ClarityIssue(
            "param-name", "data", "Use a domain-specific name", Severity.MEDIUM, 2, 4.0
        )
        json = export([("S", _result(issues=[issue]))])
        assert '"category":"param-name"' in json
        assert '"element":"data"' in json
        assert '"severity":"MEDIUM"' in json
        assert '"occurrences":2' in json
        assert '"impactScore":4.00' in json

    def test_string_escaping(self) -> None:
        issue = ClarityIssue("c", 'do"stuff', "Use a \\proper\\ name", Severity.LOW, 1, 1.0)
        json = export([('Scenario with "quotes"', _result(issues=[issue]))])
        assert '"name":"Scenario with \\"quotes\\""' in json
        assert '"element":"do\\"stuff"' in json
        assert '"suggestion":"Use a \\\\proper\\\\ name"' in json

    def test_multiple_scenarios_preserve_duplicates(self) -> None:
        json = export([("dup", _result()), ("dup", _result())])
        assert "},{" in json


class TestReport:
    def test_suite_report_header_and_sort(self) -> None:
        report = render_suite_report(
            [("HighScore", _result(0.95)), ("LowScore", _result(0.40, [_issue()]))]
        )
        assert report.startswith("# Clarity Suite Report")
        assert "## Scenarios" in report
        # ascending sort → LowScore row precedes HighScore row
        assert report.index("| LowScore |") < report.index("| HighScore |")

    def test_low_score_detail_block_emitted(self) -> None:
        report = render_suite_report([("LowScore", _result(0.40, [_issue()]))])
        assert "### LowScore" in report
        assert "| Method Names | 0.90 | 0.30 | 0.27 |" in report

    def test_high_score_has_no_detail_block(self) -> None:
        report = render_suite_report([("Good", _result(0.95))])
        assert "### Good" not in report

    def test_single_report_issue_occurrence_marker(self) -> None:
        issue = ClarityIssue("param-name", "data", "fix it", Severity.MEDIUM, 3, 6.0)
        report = render("Scenario", _result(0.4, [issue]))
        assert "`data` (x3)" in report


def _issue() -> ClarityIssue:
    return ClarityIssue("method-name", "A.do", "use a verb", Severity.HIGH, 1, 3.0)
