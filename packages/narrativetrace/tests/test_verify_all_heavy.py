# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Row builders for the heavy/scheduled-cadence categories `mutation`, `fuzz-tier-b`,
`benchmarks`, `allocation` (`scripts/verify_all_heavy.py`).
"""

from __future__ import annotations

from pathlib import Path

from scripts.verify_all_exec import CommandOutcome
from scripts.verify_all_heavy import (
    MutationPackageResult,
    build_allocation_row,
    build_benchmarks_row,
    build_benchmarks_skipped_row,
    build_fuzz_tier_b_row,
    build_mutation_row,
)


def _outcome(output: str = "", exit_code: int = 0) -> CommandOutcome:
    return CommandOutcome(exit_code=exit_code, output=output, seconds=90.0, log_file=Path("x.log"))


def _package(
    name: str, killed: int | None, scored: int | None, exit_code: int = 0
) -> MutationPackageResult:
    return MutationPackageResult(
        name=name,
        outcome=_outcome(exit_code=exit_code),
        killed=killed,
        scored=scored,
        excluded=0,
        total=scored,
        survived=None if scored is None else scored - killed,  # type: ignore[operator]
        no_tests=0,
        timeout=0,
    )


class TestBuildMutationRow:
    def test_combines_both_packages_kill_counts_into_one_score(self) -> None:
        nt = _package("narrativetrace", killed=90, scored=100)
        glossary = _package("narrativetrace-glossary", killed=45, scored=50)
        row = build_mutation_row(nt, glossary)
        assert row.status == "passed"
        assert row.metrics["mutants_killed"] == 135
        assert row.metrics["mutation_score"] == 90.0

    def test_failed_when_either_packages_gate_exited_nonzero(self) -> None:
        nt = _package("narrativetrace", killed=90, scored=100, exit_code=1)
        glossary = _package("narrativetrace-glossary", killed=45, scored=50)
        row = build_mutation_row(nt, glossary)
        assert row.status == "failed"

    def test_a_crashed_package_with_no_score_still_produces_a_row(self) -> None:
        nt = _package("narrativetrace", killed=None, scored=None, exit_code=1)
        glossary = _package("narrativetrace-glossary", killed=45, scored=50)
        row = build_mutation_row(nt, glossary)
        assert row.status == "failed"
        assert "mutants_killed" not in row.metrics
        assert row.note is not None
        assert "crashed before producing a score" in row.note


class TestBuildFuzzTierBRow:
    def test_parses_the_hypothesis_only_summary_when_atheris_is_unavailable(self) -> None:
        output = (
            "TIER B: atheris is not importable on this interpreter/platform — running the "
            "budgeted Hypothesis fallback\n"
            "poe fuzz: 31821 examples across 8 properties in 26.2s (floor: 20000 examples)\n"
        )
        row = build_fuzz_tier_b_row(_outcome(output, exit_code=0))
        assert row.status == "passed"
        assert row.metrics["examples"] == 31821
        assert row.metrics["properties_run"] == 8
        assert row.metrics["targets_fuzzed"] == 0
        assert "atheris" in row.tool

    def test_parses_the_atheris_line_when_available(self) -> None:
        output = (
            "TIER B: atheris IS importable on this interpreter — running a real\n"
            "poe fuzz (atheris, target 1): 70571 executions in 15.0s (floor: 50/s)\n"
            "poe fuzz: 31821 examples across 8 properties in 26.2s (floor: 20000 examples)\n"
        )
        row = build_fuzz_tier_b_row(_outcome(output, exit_code=0))
        assert row.metrics["executions"] == 70571
        assert row.metrics["targets_fuzzed"] == 1

    def test_failed_when_the_underlying_run_exits_nonzero(self) -> None:
        row = build_fuzz_tier_b_row(_outcome("FAIL: only 10 examples ran", exit_code=1))
        assert row.status == "failed"


_BENCH_JUNIT_ALL_PASSED = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" time="5.0">
<testcase classname="packages.narrativetrace.tests.test_bench.TestX" name="test_a" time="1.0"/>
<testcase classname="packages.narrativetrace.tests.test_bench.TestX" name="test_b" time="1.0"/>
</testsuite></testsuites>
"""

_BENCH_JUNIT_ONE_REGRESSED = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" time="5.0">
<testcase classname="packages.narrativetrace.tests.test_bench.TestX" name="test_a" time="1.0"/>
<testcase classname="packages.narrativetrace.tests.test_bench.TestX" name="test_b" time="1.0">
<failure message="benchmark regressed">too slow</failure>
</testcase>
</testsuite></testsuites>
"""


class TestBuildBenchmarksRow:
    def test_passed_with_benchmarks_run_and_zero_regressions(self, tmp_path: Path) -> None:
        junit_path = tmp_path / "benchmarks.xml"
        junit_path.write_text(_BENCH_JUNIT_ALL_PASSED, encoding="utf-8")
        row = build_benchmarks_row(_outcome(exit_code=0), junit_path)
        assert row.status == "passed"
        assert row.metrics == {"benchmarks_run": 2, "regressions": 0}

    def test_failed_with_a_regression_counted(self, tmp_path: Path) -> None:
        junit_path = tmp_path / "benchmarks.xml"
        junit_path.write_text(_BENCH_JUNIT_ONE_REGRESSED, encoding="utf-8")
        row = build_benchmarks_row(_outcome(exit_code=1), junit_path)
        assert row.status == "failed"
        assert row.metrics == {"benchmarks_run": 2, "regressions": 1}

    def test_falls_back_to_empty_metrics_when_junit_is_missing(self, tmp_path: Path) -> None:
        row = build_benchmarks_row(_outcome(exit_code=1), tmp_path / "missing.xml")
        assert row.metrics == {}


class TestBuildBenchmarksSkippedRow:
    def test_status_skipped_with_the_load_average_in_the_note(self) -> None:
        row = build_benchmarks_skipped_row(load_average=16.9, threshold=6.0)
        assert row.status == "skipped"
        assert row.duration_seconds == 0.0
        assert "16.9" in (row.note or "")


class TestBuildAllocationRow:
    def test_is_always_not_implemented(self) -> None:
        row = build_allocation_row()
        assert row.status == "not-implemented"
        assert row.tool == "none"
        assert row.metrics == {}
