# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Row builders for `architecture` and the two concurrency-stress categories
(`scripts/verify_all_arch_stress.py`).
"""

from __future__ import annotations

from pathlib import Path

from scripts.verify_all_arch_stress import build_architecture_row, build_stress_short_row
from scripts.verify_all_exec import CommandOutcome

_JUNIT_ALL_PASSED = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" time="1.6">
<testcase classname="packages.narrativetrace.tests.test_pipeline_stress.TestX"
 name="test_a" time="0.8"/>
</testsuite></testsuites>
"""

_JUNIT_ONE_FAILED = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" time="1.6">
<testcase classname="packages.narrativetrace.tests.test_pipeline_stress.X" name="test_a" time="0.8">
<failure message="boom">trace</failure>
</testcase>
</testsuite></testsuites>
"""


def _outcome(exit_code: int = 0) -> CommandOutcome:
    return CommandOutcome(exit_code=exit_code, output="", seconds=1.6, log_file=Path("x.log"))


class TestBuildArchitectureRow:
    def test_passed_when_no_contracts_are_broken(self) -> None:
        outcome = CommandOutcome(
            exit_code=0,
            output="Contracts: 1 kept, 0 broken.\n",
            seconds=1.0,
            log_file=Path("x.log"),
        )
        row = build_architecture_row(outcome)
        assert row.status == "passed"
        assert row.metrics == {"contracts_kept": 1, "contracts_broken": 0}

    def test_failed_when_a_contract_is_broken(self) -> None:
        outcome = CommandOutcome(
            exit_code=1,
            output="Contracts: 0 kept, 1 broken.\n",
            seconds=1.0,
            log_file=Path("x.log"),
        )
        row = build_architecture_row(outcome)
        assert row.status == "failed"
        assert row.metrics == {"contracts_kept": 0, "contracts_broken": 1}

    def test_falls_back_to_exit_code_when_the_summary_line_is_unparseable(self) -> None:
        outcome = CommandOutcome(
            exit_code=1, output="lint-imports crashed", seconds=1.0, log_file=Path("x.log")
        )
        row = build_architecture_row(outcome)
        assert row.status == "failed"
        assert row.metrics == {}


class TestBuildStressShortRow:
    def test_passed_when_every_testcase_passed(self, tmp_path: Path) -> None:
        junit_path = tmp_path / "stress-short.xml"
        junit_path.write_text(_JUNIT_ALL_PASSED, encoding="utf-8")
        row = build_stress_short_row(_outcome(exit_code=0), junit_path)
        assert row.status == "passed"
        assert row.metrics["tests_passed"] == 1

    def test_failed_when_a_testcase_failed(self, tmp_path: Path) -> None:
        junit_path = tmp_path / "stress-short.xml"
        junit_path.write_text(_JUNIT_ONE_FAILED, encoding="utf-8")
        row = build_stress_short_row(_outcome(exit_code=1), junit_path)
        assert row.status == "failed"
        assert row.metrics["tests_failed"] == 1

    def test_falls_back_to_the_outcome_when_junit_is_missing(self, tmp_path: Path) -> None:
        row = build_stress_short_row(_outcome(exit_code=1), tmp_path / "missing.xml")
        assert row.status == "failed"
        assert row.metrics == {}
        assert row.duration_seconds == 1.6
