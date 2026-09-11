# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The JUnit-slicing predicates and parsers `poe verify-all` derives `unit-tests`, `coverage`,
`property`, `fuzz-tier-a`, and `conformance` from (`scripts/verify_all_testrun.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_all_testrun import (
    JUnitCase,
    all_green,
    is_conformance_module,
    is_property_module,
    is_security_tests_module,
    matching,
    parse_junit,
    read_coverage_totals,
    summarize,
    total_seconds,
)

_JUNIT_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
<testsuite name="pytest" errors="0" failures="1" skipped="1" tests="4" time="12.5">
<testcase classname="packages.narrativetrace.tests.test_tree_props" name="test_a" time="1.0"/>
<testcase classname="packages.narrativetrace-security-tests.tests.test_traceparent_properties"
 name="test_b" time="2.5">
<failure message="boom">Traceback</failure>
</testcase>
<testcase classname="packages.narrativetrace.tests.test_identity_conformance"
 name="test_c" time="0.5">
<skipped type="pytest.skip" message="skip"/>
</testcase>
<testcase classname="packages.narrativetrace.tests.test_render" name="test_d" time="0.1"/>
</testsuite>
</testsuites>
"""


class TestIsPropertyModule:
    def test_matches_the_props_naming_convention(self) -> None:
        assert is_property_module("packages.narrativetrace.tests.test_tree_props") is True

    def test_matches_with_a_trailing_class_name(self) -> None:
        assert is_property_module("packages.narrativetrace.tests.test_tree_props.SomeClass") is True

    def test_does_not_match_the_unrelated_properties_naming_convention(self) -> None:
        """`_props` is never a substring of `_properties` (the character right after "prop"
        differs: "s" vs "e") — a near-miss sibling worth pinning as a regression test, the same
        way any string-boundary match should be tested against its closest false positive."""
        classname = "packages.narrativetrace-security-tests.tests.test_traceparent_properties"
        assert is_property_module(classname) is False

    def test_does_not_match_a_module_with_no_props_suffix(self) -> None:
        assert is_property_module("packages.narrativetrace.tests.test_render") is False


class TestIsSecurityTestsModule:
    def test_matches_the_security_tests_package(self) -> None:
        classname = "packages.narrativetrace-security-tests.tests.test_traceparent_properties"
        assert is_security_tests_module(classname) is True

    def test_does_not_match_a_sibling_package_sharing_the_prefix(self) -> None:
        """Boundary check, not a bare prefix check: a hypothetical
        `narrativetrace-security-testsx` package must not match — the prefix ends in a literal
        `.`, which a same-prefixed-but-different package name would not immediately follow."""
        classname = "packages.narrativetrace-security-testsx.tests.test_something"
        assert is_security_tests_module(classname) is False

    def test_does_not_match_the_core_package(self) -> None:
        assert is_security_tests_module("packages.narrativetrace.tests.test_render") is False


class TestIsConformanceModule:
    def test_matches_test_conformance(self) -> None:
        assert (
            is_conformance_module("packages.narrativetrace-pytest.tests.test_conformance") is True
        )

    def test_matches_test_identity_conformance(self) -> None:
        assert (
            is_conformance_module("packages.narrativetrace.tests.test_identity_conformance") is True
        )

    def test_does_not_match_a_fused_near_miss_with_no_separating_underscore(self) -> None:
        """`test_nonconformance` (fused, not underscore-delimited) is the near-miss sibling —
        proper boundary checking requires a delimiter, not a bare substring test."""
        assert is_conformance_module("packages.narrativetrace.tests.test_nonconformance") is False

    def test_does_not_match_an_unrelated_module(self) -> None:
        assert is_conformance_module("packages.narrativetrace.tests.test_render") is False


class TestParseJunit:
    def test_reads_every_testcase_and_the_suites_own_time(self, tmp_path: Path) -> None:
        path = tmp_path / "unit-tests.xml"
        path.write_text(_JUNIT_FIXTURE, encoding="utf-8")

        entries, suite_seconds = parse_junit(path)

        assert len(entries) == 4
        assert suite_seconds == 12.5

    def test_classifies_failure_skipped_and_passed_outcomes(self, tmp_path: Path) -> None:
        path = tmp_path / "unit-tests.xml"
        path.write_text(_JUNIT_FIXTURE, encoding="utf-8")
        entries, _ = parse_junit(path)

        by_name = {e.name: e.outcome for e in entries}

        assert by_name["test_a"] == "passed"
        assert by_name["test_b"] == "failed"
        assert by_name["test_c"] == "skipped"
        assert by_name["test_d"] == "passed"

    def test_a_suite_with_no_testsuite_element_reports_zero_time(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.xml"
        path.write_text('<?xml version="1.0"?><testsuites/>', encoding="utf-8")

        entries, suite_seconds = parse_junit(path)

        assert entries == ()
        assert suite_seconds == 0.0


class TestMatchingAndSummarize:
    def test_matching_filters_by_predicate_on_classname(self) -> None:
        entries = (
            JUnitCase("packages.a.tests.test_x_props", "t1", 1.0, "passed"),
            JUnitCase("packages.a.tests.test_y", "t2", 2.0, "passed"),
        )
        assert matching(entries, is_property_module) == (entries[0],)

    def test_summarize_counts_outcomes_and_distinct_classes(self) -> None:
        entries = (
            JUnitCase("mod.A", "t1", 1.0, "passed"),
            JUnitCase("mod.A", "t2", 1.0, "failed"),
            JUnitCase("mod.B", "t3", 1.0, "skipped"),
        )
        assert summarize(entries) == {
            "tests_passed": 1,
            "tests_failed": 1,
            "tests_skipped": 1,
            "test_classes": 2,
        }

    def test_summarize_of_an_empty_slice_is_all_zeros(self) -> None:
        assert summarize(()) == {
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "test_classes": 0,
        }

    def test_total_seconds_sums_only_the_matched_entries(self) -> None:
        entries = (
            JUnitCase("mod.A", "t1", 1.5, "passed"),
            JUnitCase("mod.A", "t2", 2.5, "passed"),
        )
        assert total_seconds(entries) == 4.0

    def test_all_green_is_false_when_anything_failed(self) -> None:
        entries = (JUnitCase("mod.A", "t1", 1.0, "passed"), JUnitCase("mod.A", "t2", 1.0, "failed"))
        assert all_green(entries) is False

    def test_all_green_is_vacuously_true_for_an_empty_slice(self) -> None:
        assert all_green(()) is True


class TestReadCoverageTotals:
    def test_reads_the_three_totals_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "coverage.json"
        path.write_text(
            json.dumps(
                {"totals": {"percent_covered": 97.5, "covered_lines": 100, "missing_lines": 3}}
            ),
            encoding="utf-8",
        )

        totals = read_coverage_totals(path)

        assert totals.coverage_pct == 97.5
        assert totals.lines_covered == 100
        assert totals.lines_missed == 3
