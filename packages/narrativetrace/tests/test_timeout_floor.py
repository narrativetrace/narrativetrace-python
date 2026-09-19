# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/timeout_floor.py`'s pure decision logic.

`main()`'s glue (reading the real allowlist, printing, exit code) is exercised for real by
`poe timeout-floor` / `poe check` running the gate against this repository; these tests drive
`find_sub_floor_markers` and `check` in isolation against synthetic fixture trees under
`tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

from scripts.timeout_floor import (
    ALLOWLIST_PATH,
    REPO_ROOT,
    TIMEOUT_FLOOR_SECONDS,
    TimeoutMarkerHit,
    _load_allowlist,
    check,
    find_sub_floor_markers,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestFindSubFloorMarkers:
    def test_a_marker_below_the_floor_is_detected(self, tmp_path: Path) -> None:
        """The planted regression this gate exists to catch: a new hang guard sized under the
        documented floor (release retrospective rule 3 refinement, Pro ledger #129)."""
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n@pytest.mark.timeout(0.5)\ndef test_deep() -> None:\n    pass\n",
        )

        hits = find_sub_floor_markers(tmp_path)

        # `func.lineno` is the `def` line, not the decorator line -- same convention as
        # `deep_fixture_budget.DeepFixtureHit`.
        assert hits == [
            TimeoutMarkerHit(test_id="packages/core/tests/test_a.py::test_deep", line=5, value=0.5)
        ]

    def test_a_marker_at_exactly_the_floor_is_not_a_violation(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n"
            f"@pytest.mark.timeout({TIMEOUT_FLOOR_SECONDS})\ndef test_deep() -> None:\n    pass\n",
        )

        assert find_sub_floor_markers(tmp_path) == []

    def test_a_marker_above_the_floor_is_not_a_violation(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n@pytest.mark.timeout(30)\ndef test_deep() -> None:\n    pass\n",
        )

        assert find_sub_floor_markers(tmp_path) == []

    def test_a_test_with_no_timeout_marker_is_not_a_violation(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_shallow() -> None:\n    pass\n",
        )

        assert find_sub_floor_markers(tmp_path) == []

    def test_an_unrelated_decorator_is_not_mistaken_for_a_timeout_marker(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n"
            '@pytest.mark.parametrize("x", [1])\ndef test_deep(x) -> None:\n    pass\n',
        )

        assert find_sub_floor_markers(tmp_path) == []

    def test_a_sub_floor_marker_on_a_method_is_detected_with_its_qualified_name(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n"
            "class TestX:\n    @pytest.mark.timeout(1)\n    def test_deep(self) -> None:\n"
            "        pass\n",
        )

        assert [hit.test_id for hit in find_sub_floor_markers(tmp_path)] == [
            "packages/core/tests/test_a.py::TestX.test_deep"
        ]

    def test_a_non_numeric_timeout_argument_is_ignored_not_crashed_on(self, tmp_path: Path) -> None:
        """`pytest.mark.timeout` also accepts a `method=` keyword and non-literal expressions in
        principle; this gate only judges the literal-number shape every marker in this repo
        actually uses, and must not crash on anything else."""
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\nBUDGET = 0.5\n\n\n"
            "@pytest.mark.timeout(BUDGET)\ndef test_deep() -> None:\n    pass\n",
        )

        assert find_sub_floor_markers(tmp_path) == []


class TestCheck:
    def test_reports_a_sub_floor_hit_as_a_violation_and_never_flags_an_allowlisted_one(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n@pytest.mark.timeout(0.5)\ndef test_deep() -> None:\n    pass\n",
        )
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_b.py",
            "import pytest\n\n\n@pytest.mark.timeout(0.5)\n"
            "def test_also_deep() -> None:\n    pass\n",
        )

        result = check(
            tmp_path, {"packages/core/tests/test_b.py::test_also_deep": "reasoned exception"}
        )

        assert [hit.test_id for hit in result.violations] == [
            "packages/core/tests/test_a.py::test_deep"
        ]
        assert result.stale_allowlist_entries == ()

    def test_flags_an_allowlist_entry_whose_test_no_longer_carries_a_sub_floor_marker_as_stale(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_x() -> None:\n    pass\n",
        )

        result = check(tmp_path, {"packages/core/tests/test_a.py::test_x": "no longer needed"})

        assert result.violations == ()
        assert result.stale_allowlist_entries == ("packages/core/tests/test_a.py::test_x",)

    def test_is_clean_when_nothing_matches_and_nothing_is_allowlisted(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_x() -> None:\n    pass\n",
        )

        result = check(tmp_path, {})

        assert result.violations == ()
        assert result.stale_allowlist_entries == ()

    def test_is_clean_against_the_real_repository_allowlist(self) -> None:
        """The live gate: every `@pytest.mark.timeout(...)` marker actually committed in this
        repository meets the documented floor, with no allowlist exceptions needed (2026-09-18,
        Pro ledger #129 sweep)."""
        result = check(REPO_ROOT, _load_allowlist(ALLOWLIST_PATH))

        assert result.violations == ()
        assert result.stale_allowlist_entries == ()
