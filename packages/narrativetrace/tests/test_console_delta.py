# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the "Since last green" suite-footer line and the delta-aware failure report —
:meth:`~narrativetrace.output.reporter.ConsoleSummaryReporter.format_delta_line` and
``format_failure_report``.
"""

from __future__ import annotations

from narrativetrace.output.reporter import ConsoleSummaryReporter
from narrativetrace.output.structural_delta import Kind, ScenarioDelta

_REPORTER = ConsoleSummaryReporter()


class TestFormatDeltaLine:
    def test_empty_deltas_yields_an_empty_line(self) -> None:
        assert _REPORTER.format_delta_line([]) == ""

    def test_all_unchanged_uses_the_scenario_noun(self) -> None:
        deltas = [ScenarioDelta("a", Kind.UNCHANGED), ScenarioDelta("b", Kind.UNCHANGED)]
        assert _REPORTER.format_delta_line(deltas) == "2 scenarios unchanged"

    def test_a_single_unchanged_scenario_is_singular(self) -> None:
        deltas = [ScenarioDelta("a", Kind.UNCHANGED)]
        assert _REPORTER.format_delta_line(deltas) == "1 scenario unchanged"

    def test_new_scenarios_get_their_own_segment(self) -> None:
        deltas = [ScenarioDelta("a", Kind.NEW)]
        assert _REPORTER.format_delta_line(deltas) == "1 scenario new"

    def test_the_noun_rides_only_on_the_first_segment(self) -> None:
        deltas = [ScenarioDelta("a", Kind.UNCHANGED), ScenarioDelta("b", Kind.NEW)]
        assert _REPORTER.format_delta_line(deltas) == "1 scenario unchanged · 1 new"

    def test_changed_scenarios_describe_their_summary(self) -> None:
        deltas = [ScenarioDelta("Weekend trip", Kind.CHANGED, "+4 calls X.y")]
        assert (
            _REPORTER.format_delta_line(deltas)
            == '1 scenario changed: "Weekend trip" (+4 calls X.y)'
        )

    def test_a_long_scenario_name_is_truncated_at_32_characters(self) -> None:
        long_name = "a" * 40
        deltas = [ScenarioDelta(long_name, Kind.CHANGED, "+1 call X.y")]
        rendered = _REPORTER.format_delta_line(deltas)
        assert ("a" * 32 + "…") in rendered
        assert long_name not in rendered

    def test_all_three_kinds_together(self) -> None:
        deltas = [
            ScenarioDelta("a", Kind.UNCHANGED),
            ScenarioDelta("b", Kind.NEW),
            ScenarioDelta("c", Kind.CHANGED, "+1 call X.y"),
        ]
        assert _REPORTER.format_delta_line(deltas) == (
            '1 scenario unchanged · 1 new · 1 changed: "c" (+1 call X.y)'
        )


class TestFormatFailureReport:
    def test_a_changed_delta_prints_the_summary_and_diff_instead_of_the_full_trace(self) -> None:
        delta = ScenarioDelta("s", Kind.CHANGED, "+1 call X.y", "+- X.y()\n")
        report = _REPORTER.format_failure_report("s", "full trace text", delta)
        assert "Changed since last green (+1 call X.y):" in report
        assert "+- X.y()" in report
        assert "full trace text" not in report

    def test_an_unchanged_delta_points_at_values_and_assertions(self) -> None:
        delta = ScenarioDelta("s", Kind.UNCHANGED)
        report = _REPORTER.format_failure_report("s", "full trace text", delta)
        assert "Structure unchanged since last green" in report
        assert "full trace text" in report

    def test_a_new_delta_falls_back_to_the_plain_trace_report(self) -> None:
        delta = ScenarioDelta("s", Kind.NEW)
        report = _REPORTER.format_failure_report("s", "full trace text", delta)
        assert report == "\n\ns\n\nExecution trace:\nfull trace text"

    def test_no_delta_at_all_falls_back_to_the_plain_trace_report(self) -> None:
        report = _REPORTER.format_failure_report("s", "full trace text", None)
        assert report == "\n\ns\n\nExecution trace:\nfull trace text"
