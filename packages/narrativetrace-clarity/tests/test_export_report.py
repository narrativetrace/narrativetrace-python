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


class TestReportCellsStayInTheirTable:
    """B-226: a scenario name or issue field with a pipe or a line break must not forge a cell or
    a row of the suite report's tables."""

    def test_a_pipe_and_a_newline_in_a_scenario_name_stay_in_one_row(self) -> None:
        report = render_suite_report([("a | b\n| forged | 9.99 |", _result(0.95))])
        rows = [line for line in report.splitlines() if line.startswith("| a")]
        assert rows == [r"| a \| b \| forged \| 9.99 \| | 0.95 |"]

    def test_a_pipe_and_a_newline_in_an_issue_element_stay_in_one_row(self) -> None:
        issue = ClarityIssue("cat", "x|y\nz", "do it", Severity.HIGH, 1, 3.0)
        report = render("S", _result(0.4, [issue]))
        assert [line for line in report.splitlines() if line.startswith("| HIGH")] == [
            "| HIGH | cat | `x%7Cy z` | do it |"
        ]

    def test_a_pipe_and_a_newline_in_a_suggestion_and_category_stay_in_one_row(self) -> None:
        issue = ClarityIssue("c|at\negory", "e", "su|gg\r\nest", Severity.LOW, 2, 1.0)
        report = render("S", _result(0.4, [issue]))
        assert [line for line in report.splitlines() if line.startswith("| LOW")] == [
            "| LOW | c\\|at egory | `e` (x2) | su\\|gg est |"
        ]

    def test_a_backslash_before_a_pipe_in_a_suggestion_keeps_the_row_whole(self) -> None:
        issue = ClarityIssue("cat", "e", "a\\|b", Severity.LOW, 1, 1.0)
        report = render("S", _result(0.4, [issue]))
        assert [line for line in report.splitlines() if line.startswith("| LOW")] == [
            "| LOW | cat | `e` | a\\\\\\|b |"
        ]

    def test_a_newline_in_a_scenario_name_stays_in_the_single_report_and_detail_headings(
        self,
    ) -> None:
        issue = ClarityIssue("c", "e", "s", Severity.LOW, 1, 1.0)
        single = render("one\n## forged", _result(0.4, [issue]))
        suite = render_suite_report([("one\n## forged", _result(0.4, [issue]))])
        assert single.splitlines()[0] == "# Clarity Report: one ## forged"
        assert "### one ## forged" in suite.splitlines()
