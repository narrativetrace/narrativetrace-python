# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`poe verify-all`'s own orchestration (`scripts/verify_all.py`) — the safety net that keeps
one crashing category from taking down the whole run, and the structural guarantee that every
one of SCHEMA.md's 21 fixed category ids is actually produced by some step, exactly once.
"""

from __future__ import annotations

from scripts.verify_all import _STEPS, _crash_row, _safe
from scripts.verify_all_schema import CATEGORIES, CategoryResult


class TestCrashRow:
    def test_produces_a_failed_row_naming_the_category_and_the_exception(self) -> None:
        row = _crash_row("lint", ValueError("boom"))
        assert row.category == "lint"
        assert row.status == "failed"
        assert "boom" in (row.note or "")


class TestSafe:
    def test_returns_the_producers_own_rows_on_success(self) -> None:
        rows = _safe(("lint",), lambda: [_crash_row("lint", ValueError("unused"))])
        assert len(rows) == 1

    def test_a_raising_producer_yields_one_failed_row_per_declared_category(self) -> None:
        def boom() -> list[CategoryResult]:
            raise RuntimeError("tool exploded")

        rows = _safe(("secrets", "sast", "sca"), boom)

        assert [row.category for row in rows] == ["secrets", "sast", "sca"]
        assert all(row.status == "failed" for row in rows)
        assert all("tool exploded" in (row.note or "") for row in rows)


class TestStepsCoverEveryFixedCategoryExactlyOnce:
    def test_the_sweep_plus_declared_steps_account_for_all_21_categories(self) -> None:
        sweep_categories = ("unit-tests", "property", "fuzz-tier-a", "conformance", "coverage")
        declared = [category for category_ids, _producer in _STEPS for category in category_ids]

        all_ids = list(sweep_categories) + declared

        assert sorted(all_ids) == sorted(CATEGORIES)
        assert len(all_ids) == len(set(all_ids)) == len(CATEGORIES)
