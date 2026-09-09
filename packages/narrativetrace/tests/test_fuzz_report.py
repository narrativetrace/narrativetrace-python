# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`poe fuzz`'s honesty gate (`scripts/fuzz_report.py`).

Exercises the pure detection/parsing/scoring logic in isolation. `run_hypothesis_sweep()`'s/
`run_atheris_target()`'s subprocess glue and `main()` are exercised by actually running
`poe fuzz`, not here — mirrors `test_mutation_gate.py`/`test_run_security_tool.py`'s own split.
"""

from __future__ import annotations

from scripts.fuzz_report import (
    AtherisRunReport,
    FuzzRunReport,
    atheris_status_message,
    module_importable,
    parse_atheris_executions,
    parse_example_counts,
)


class TestModuleImportable:
    def test_true_for_a_module_that_exists(self) -> None:
        assert module_importable("sys") is True

    def test_false_for_a_module_that_does_not_exist(self) -> None:
        assert module_importable("definitely_not_a_real_module_xyz") is False


class TestAtherisStatusMessage:
    def test_names_the_fallback_when_unavailable(self) -> None:
        message = atheris_status_message(available=False)

        assert "not importable" in message
        assert "Hypothesis fallback" in message

    def test_names_the_real_fuzz_when_available(self) -> None:
        message = atheris_status_message(available=True)

        assert "IS importable" in message
        assert "real, time-boxed coverage-guided fuzz" in message


class TestParseAtherisExecutions:
    def test_none_when_no_stats_line_is_present(self) -> None:
        """The harness crashed or failed to start before libFuzzer printed its own summary."""
        assert parse_atheris_executions("Traceback (most recent call last):\n") is None

    def test_reads_the_executed_units_stat(self) -> None:
        output = (
            "Done 70571 runs in 16 second(s)\n"
            "stat::number_of_executed_units: 70571\n"
            "stat::average_exec_per_sec:     4410\n"
        )

        assert parse_atheris_executions(output) == 70571


class TestAtherisRunReportIsCredible:
    def test_true_when_throughput_clears_the_floor(self) -> None:
        report = AtherisRunReport(executions=70_571, duration_seconds=16.0)

        assert report.is_credible is True

    def test_false_when_no_executions_were_ever_reported(self) -> None:
        """The exact shape of a harness that crashed on the first input: no stats line at all."""
        report = AtherisRunReport(executions=None, duration_seconds=0.4)

        assert report.is_credible is False

    def test_false_when_throughput_falls_short_of_the_floor(self) -> None:
        # 60s budget, only 100 executions -- far below the 50/s floor.
        report = AtherisRunReport(executions=100, duration_seconds=60.0)

        assert report.is_credible is False

    def test_summary_reports_executions_and_duration(self) -> None:
        report = AtherisRunReport(executions=70_571, duration_seconds=16.0)

        summary = report.summary()

        assert "70571" in summary
        assert "16.0s" in summary


class TestParseExampleCounts:
    def test_empty_output_yields_no_counts(self) -> None:
        assert parse_example_counts("") == []

    def test_sums_passing_failing_and_invalid_per_property(self) -> None:
        text = "  - 5000 passing examples, 0 failing examples, 0 invalid examples\n"

        assert parse_example_counts(text) == [5000]

    def test_one_entry_per_reported_property_in_order(self) -> None:
        text = (
            "  - 5000 passing examples, 0 failing examples, 0 invalid examples\n"
            "  - 4683 passing examples, 0 failing examples, 317 invalid examples\n"
            "  - 200 passing examples, 0 failing examples, 0 invalid examples\n"
        )

        assert parse_example_counts(text) == [5000, 5000, 200]

    def test_a_failing_example_still_counts_toward_the_total(self) -> None:
        text = "  - 42 passing examples, 1 failing examples, 0 invalid examples\n"

        assert parse_example_counts(text) == [43]


class TestFuzzRunReportIsCredible:
    def test_true_at_or_above_the_floor(self) -> None:
        report = FuzzRunReport(total_examples=20_000, property_count=8, duration_seconds=55.0)

        assert report.is_credible is True

    def test_false_below_the_floor(self) -> None:
        report = FuzzRunReport(total_examples=19_999, property_count=8, duration_seconds=55.0)

        assert report.is_credible is False

    def test_false_for_a_run_that_collected_nothing(self) -> None:
        """The exact shape of the previously-caught incident: a fast, empty, zero-example run."""
        report = FuzzRunReport(total_examples=0, property_count=0, duration_seconds=0.3)

        assert report.is_credible is False

    def test_summary_reports_examples_property_count_and_duration(self) -> None:
        report = FuzzRunReport(total_examples=31_202, property_count=8, duration_seconds=61.1)

        summary = report.summary()

        assert "31202" in summary
        assert "8 properties" in summary
        assert "61.1s" in summary
