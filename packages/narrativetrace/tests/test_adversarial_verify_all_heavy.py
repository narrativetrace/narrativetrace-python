# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial tests for verify_all_heavy.py: vendor-validation row parsing edge cases."""

from __future__ import annotations

from pathlib import Path

from scripts.verify_all_exec import CommandOutcome
from scripts.verify_all_heavy import build_vendor_validation_row


def _outcome(output: str = "", exit_code: int = 0) -> CommandOutcome:
    return CommandOutcome(exit_code=exit_code, output=output, seconds=10.0, log_file=Path("x.log"))


class TestBuildVendorValidationRowAdversarial:
    """Adversarial parsing of vendor-validation output."""

    def test_output_with_both_skipped_and_passed_patterns(self) -> None:
        """Malformed output containing both SKIPPED and passed patterns."""
        output = (
            "vendor-validate: every row SKIPPED — nothing was validated\n"
            "vendor-validate: 1/1 rows passed\n"
        )
        # Exit code zero, but output is contradictory
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        # Should parse "every row SKIPPED" first and treat as skipped
        # (SKIPPED check comes before rows_passed check in the code)
        assert row.status == "skipped"
        assert "rows_passed" not in row.metrics

    def test_output_with_neither_skipped_nor_passed_pattern(self) -> None:
        """Output with exit code zero but neither status pattern found."""
        output = "vendor-validate: something unexpected happened\n"
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        # Should be treated as passed (exit zero, no skip pattern found)
        assert row.status == "passed"
        # rows_passed not in metrics because pattern didn't match
        assert "rows_passed" not in row.metrics
        assert row.metrics["rows"] == 1

    def test_output_with_multiple_rows_passed_lines(self) -> None:
        """Output containing multiple "rows passed" lines (first match wins)."""
        output = (
            "vendor-validate: fake passed — validated\n"
            "vendor-validate: 2/5 rows passed\n"
            "vendor-validate: 3/5 rows passed\n"
        )
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        assert row.status == "passed"
        # First match wins (regex.search finds the first occurrence, not the last)
        assert row.metrics["rows_passed"] == 2

    def test_output_with_rows_passed_pattern_but_nonzero_exit(self) -> None:
        """Exit code nonzero takes precedence over rows_passed in output."""
        output = "vendor-validate: 5/5 rows passed\n"
        row = build_vendor_validation_row(_outcome(output, exit_code=1))

        # Exit code nonzero means failed, even if output says passed
        assert row.status == "failed"
        # rows_passed still shouldn't be set when status is failed
        assert "rows_passed" not in row.metrics

    def test_malformed_rows_passed_pattern(self) -> None:
        """Rows passed pattern with unexpected format."""
        output = "vendor-validate: abc/xyz rows passed\n"  # Not numbers
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        # Pattern won't match, so status is passed but rows_passed not set
        assert row.status == "passed"
        assert "rows_passed" not in row.metrics

    def test_rows_passed_with_leading_zeros(self) -> None:
        """Rows passed numbers with leading zeros."""
        output = "vendor-validate: 007/010 rows passed\n"
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        assert row.status == "passed"
        # Leading zeros should parse as integers
        assert row.metrics["rows_passed"] == 7

    def test_very_large_rows_numbers(self) -> None:
        """Very large row numbers (edge case but should parse)."""
        output = "vendor-validate: 999999/999999 rows passed\n"
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        assert row.status == "passed"
        assert row.metrics["rows_passed"] == 999999

    def test_single_passed_row(self) -> None:
        """Single row passed (1/1)."""
        output = "vendor-validate: 1/1 rows passed\n"
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        assert row.status == "passed"
        assert row.metrics["rows_passed"] == 1

    def test_zero_rows_passed(self) -> None:
        """Zero rows passed (0/5)."""
        output = "vendor-validate: 0/5 rows passed\n"
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        # Exit zero and pattern matches
        assert row.status == "passed"
        assert row.metrics["rows_passed"] == 0

    def test_skipped_pattern_substring_in_longer_text(self) -> None:
        """SKIPPED pattern embedded in longer text."""
        output = "something vendor-validate: every row SKIPPED — something else\nmore text here\n"
        row = build_vendor_validation_row(_outcome(output, exit_code=0))

        # Pattern search should find it even with context
        assert row.status == "skipped"

    def test_empty_output_with_zero_exit(self) -> None:
        """Empty output with exit code zero."""
        row = build_vendor_validation_row(_outcome("", exit_code=0))

        # No pattern found, exit zero = passed
        assert row.status == "passed"
        assert row.metrics["rows"] == 1
        assert "rows_passed" not in row.metrics

    def test_metrics_always_contains_rows_count(self) -> None:
        """Metrics should always have 'rows' key (from CHECKS)."""
        row = build_vendor_validation_row(_outcome("garbage", exit_code=0))
        assert "rows" in row.metrics
        assert row.metrics["rows"] == 1
