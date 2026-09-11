# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The cross-port verification-report contract (`scripts/verify_all_schema.py`).

Exercises the pure JSON/Markdown serialization in isolation — `poe verify-all` actually running
every category for real is exercised by running it, not here (mirrors
`test_mutation_gate.py`/`test_run_security_tool.py`'s own split between tested pure logic and
exercised-for-real glue).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.verify_all_schema import (
    CategoryResult,
    VerificationRun,
    overall_status,
    read_verification_json,
    render_markdown,
    to_report_json,
    write_verification_json,
)


def _row(category: str = "lint", status: str = "passed", **overrides: object) -> CategoryResult:
    defaults: dict[str, object] = {
        "category": category,
        "tool": "Ruff",
        "status": status,
        "metrics": {},
        "duration_seconds": 1.5,
        "note": None,
    }
    defaults.update(overrides)
    return CategoryResult(**defaults)  # type: ignore[arg-type]


class TestCategoryResultValidation:
    def test_rejects_a_category_id_outside_the_fixed_vocabulary(self) -> None:
        with pytest.raises(ValueError, match="not a fixed category id"):
            _row(category="not-a-real-category")

    def test_rejects_a_status_outside_the_fixed_vocabulary(self) -> None:
        with pytest.raises(ValueError, match="not a fixed status"):
            _row(status="ok")

    def test_accepts_every_fixed_status(self) -> None:
        for status in ("passed", "failed", "skipped", "not-implemented"):
            _row(status=status)  # must not raise


class TestOverallStatus:
    def test_passed_when_every_row_passed_or_was_not_implemented(self) -> None:
        rows = (_row(status="passed"), _row(category="types", status="not-implemented"))
        assert overall_status(rows) == "passed"

    def test_skipped_never_taints_overall_status(self) -> None:
        rows = (_row(status="passed"), _row(category="secrets", status="skipped"))
        assert overall_status(rows) == "passed"

    def test_failed_when_at_least_one_row_failed(self) -> None:
        rows = (_row(status="passed"), _row(category="sca", status="failed"))
        assert overall_status(rows) == "failed"

    def test_empty_categories_is_vacuously_passed(self) -> None:
        assert overall_status(()) == "passed"


class TestToReportJson:
    def test_carries_every_schema_field_with_the_exact_names(self) -> None:
        run = VerificationRun(
            runtime="python",
            version="0.1.1",
            commit="abc1234",
            host="host-arm64",
            started_at="2026-09-09T00:00:00+00:00",
            ended_at="2026-09-09T00:01:00+00:00",
            categories=(_row(),),
        )
        document = to_report_json(run)
        assert set(document.keys()) == {
            "runtime",
            "version",
            "commit",
            "host",
            "started_at",
            "ended_at",
            "overall_status",
            "categories",
        }
        assert document["overall_status"] == "passed"
        row = document["categories"][0]  # type: ignore[index]
        assert set(row.keys()) == {
            "category",
            "tool",
            "status",
            "metrics",
            "duration_seconds",
            "note",
        }

    def test_a_not_implemented_row_carries_a_none_tool_note_but_no_metrics(self) -> None:
        run = VerificationRun(
            runtime="python",
            version="0.1.1",
            commit="abc1234",
            host="host-arm64",
            started_at="t0",
            ended_at="t1",
            categories=(
                _row(
                    category="types",
                    tool="none",
                    status="not-implemented",
                    metrics={},
                    duration_seconds=0.0,
                    note="no standalone type checker",
                ),
            ),
        )
        row = to_report_json(run)["categories"][0]  # type: ignore[index]
        assert row == {
            "category": "types",
            "tool": "none",
            "status": "not-implemented",
            "metrics": {},
            "duration_seconds": 0.0,
            "note": "no standalone type checker",
        }


class TestWriteAndReadVerificationJson:
    def test_write_then_read_round_trips_the_document(self, tmp_path: Path) -> None:
        run = VerificationRun(
            runtime="python",
            version="0.1.1",
            commit="abc1234",
            host="host-arm64",
            started_at="t0",
            ended_at="t1",
            categories=(_row(),),
        )
        path = tmp_path / "reports" / "verification" / "2026-09-09.json"
        write_verification_json(run, path)

        document = read_verification_json(path)

        assert document["runtime"] == "python"
        assert json.loads(path.read_text(encoding="utf-8")) == document

    def test_creates_missing_parent_directories(self, tmp_path: Path) -> None:
        run = VerificationRun(
            runtime="python",
            version="0.1.1",
            commit="c",
            host="h",
            started_at="t0",
            ended_at="t1",
            categories=(),
        )
        path = tmp_path / "a" / "b" / "c.json"
        write_verification_json(run, path)
        assert path.is_file()


class TestRenderMarkdown:
    def test_renders_from_the_written_json_not_a_separate_computation(self, tmp_path: Path) -> None:
        run = VerificationRun(
            runtime="python",
            version="0.1.1",
            commit="abc1234",
            host="host-arm64",
            started_at="2026-09-09T00:00:00+00:00",
            ended_at="2026-09-09T00:01:00+00:00",
            categories=(_row(metrics={"findings": 0}), _row(category="sca", status="failed")),
        )
        path = tmp_path / "2026-09-09.json"
        write_verification_json(run, path)

        markdown = render_markdown(path)

        assert "# Verification run — python 0.1.1" in markdown
        assert "commit: `abc1234`" in markdown
        assert "overall status: failed" in markdown
        assert "| lint | Ruff | passed | 1.5 | findings=0 |  |" in markdown
        assert "**FAILED**" in markdown

    def test_a_null_note_renders_as_an_empty_cell(self, tmp_path: Path) -> None:
        run = VerificationRun(
            runtime="python",
            version="0.1.1",
            commit="c",
            host="h",
            started_at="t0",
            ended_at="t1",
            categories=(_row(note=None),),
        )
        path = tmp_path / "r.json"
        write_verification_json(run, path)

        assert markdown_ends_each_row_with_empty_note(render_markdown(path))


def markdown_ends_each_row_with_empty_note(markdown: str) -> bool:
    data_rows = [line for line in markdown.splitlines() if line.startswith("| lint")]
    return all(line.endswith("|  |") for line in data_rows)
