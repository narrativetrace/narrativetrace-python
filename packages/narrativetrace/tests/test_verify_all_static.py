# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Row builders for the static-analysis categories (`scripts/verify_all_static.py`). Each
`run_*` function's real subprocess invocation is exercised by actually running
`poe verify-all`, not here — only the outcome-to-row translation is under test.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_all_exec import CommandOutcome
from scripts.verify_all_static import (
    build_clarity_row,
    build_complexity_row,
    build_format_row,
    build_lint_row,
    build_translation_row,
    build_types_row,
)


def _outcome(output: str = "", exit_code: int = 0, log_file: Path | None = None) -> CommandOutcome:
    return CommandOutcome(
        exit_code=exit_code, output=output, seconds=2.5, log_file=log_file or Path("x.log")
    )


class TestBuildFormatRow:
    def test_passed_when_ruff_format_check_exits_zero(self) -> None:
        row = build_format_row(_outcome(exit_code=0), "0.6.0")
        assert row.status == "passed"
        assert row.metrics == {}
        assert "Ruff 0.6.0" in row.tool

    def test_failed_when_ruff_format_check_exits_nonzero(self) -> None:
        row = build_format_row(_outcome(exit_code=1), "0.6.0")
        assert row.status == "failed"


class TestBuildLintRow:
    def test_findings_count_comes_from_the_parsed_violation_list(self) -> None:
        violations: list[dict[str, object]] = [{"code": "F401"}, {"code": "E501"}]
        row = build_lint_row(_outcome(exit_code=1), violations, "0.6.0")
        assert row.status == "failed"
        assert row.metrics == {"findings": 2}

    def test_zero_findings_is_passed(self) -> None:
        row = build_lint_row(_outcome(exit_code=0), [], "0.6.0")
        assert row.status == "passed"
        assert row.metrics == {"findings": 0}


class TestBuildComplexityRow:
    def test_passed_when_xenon_clean_and_no_plr0915_findings(self) -> None:
        row = build_complexity_row(_outcome(exit_code=0), [])
        assert row.status == "passed"
        assert row.metrics == {"findings": 0}

    def test_failed_when_xenon_itself_fails(self) -> None:
        row = build_complexity_row(_outcome(exit_code=1), [])
        assert row.status == "failed"

    def test_failed_when_ruff_reports_a_plr0915_finding_even_if_xenon_passed(self) -> None:
        violations: list[dict[str, object]] = [{"code": "PLR0915"}, {"code": "F401"}]
        row = build_complexity_row(_outcome(exit_code=0), violations)
        assert row.status == "failed"
        assert row.metrics == {"findings": 1}


class TestBuildTypesRow:
    def test_parses_a_clean_mypy_success_line(self) -> None:
        row = build_types_row(_outcome("Success: no issues found in 302 source files\n"), "1.11.0")
        assert row.status == "passed"
        assert row.metrics == {"findings": 0}
        assert row.note == "302 source files checked"

    def test_parses_an_error_count_from_a_failing_run(self) -> None:
        output = "x.py:1: error: bad\nFound 3 errors in 2 files (checked 302 source files)\n"
        row = build_types_row(_outcome(output, exit_code=1), "1.11.0")
        assert row.status == "failed"
        assert row.metrics == {"findings": 3}

    def test_omits_findings_when_the_summary_line_is_unparseable(self) -> None:
        row = build_types_row(_outcome("mypy crashed", exit_code=2), "1.11.0")
        assert row.metrics == {}


class TestBuildTranslationRow:
    def test_passed_with_no_metrics_and_no_note_when_nothing_is_unreviewed(self) -> None:
        row = build_translation_row(_outcome("translation-check: all in sync\n"))
        assert row.status == "passed"
        assert row.metrics == {}
        assert row.note is None

    def test_reports_the_unreviewed_count_as_an_informational_note_not_a_failure(self) -> None:
        output = "translation-check: 27 translated document(s) unreviewed (run ...)\n"
        row = build_translation_row(_outcome(output, exit_code=0))
        assert row.status == "passed"
        assert row.note is not None
        assert "27 translated document(s) unreviewed" in row.note


class TestBuildClarityRow:
    def test_computes_average_score_and_high_issue_count(self, tmp_path: Path) -> None:
        results_path = tmp_path / "clarity-results.json"
        results_path.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "scenarios": [
                        {"name": "A", "overallScore": 0.8, "issues": [{"severity": "HIGH"}]},
                        {"name": "B", "overallScore": 0.6, "issues": [{"severity": "LOW"}]},
                    ],
                }
            ),
            encoding="utf-8",
        )
        row = build_clarity_row(_outcome(exit_code=0), results_path)
        assert row.status == "passed"
        assert row.metrics == {"high_issues": 1, "score": 0.7}
        assert row.note == "2 class(es) scanned"

    def test_missing_results_file_falls_back_to_empty_metrics(self, tmp_path: Path) -> None:
        row = build_clarity_row(_outcome(exit_code=0), tmp_path / "missing.json")
        assert row.metrics == {}
        assert row.note is not None
