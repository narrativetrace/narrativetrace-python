# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/deep_fixture_budget.py`'s pure decision logic.

`main()`'s glue (reading the real allowlist, printing, exit code) is exercised for real by `poe
deep-fixture-budget` / `poe check` running the gate against this repository; these tests drive
`test_files`, `find_large_fixture_tests`, and `check` in isolation against synthetic fixture
trees under `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

from scripts.deep_fixture_budget import (
    DeepFixtureHit,
    check,
    find_large_fixture_tests,
)
from scripts.deep_fixture_budget import (
    test_files as _target_test_files,  # avoid pytest collecting this as a test function itself
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestTestFiles:
    def test_finds_every_test_py_file_under_packages_and_examples(self, tmp_path: Path) -> None:
        _write(tmp_path / "packages" / "core" / "tests" / "test_a.py", "")
        _write(tmp_path / "packages" / "core" / "tests" / "nested" / "test_b.py", "")
        _write(tmp_path / "examples" / "test_c.py", "")
        _write(tmp_path / "packages" / "core" / "src" / "a.py", "")  # not a test file: skipped

        found = _target_test_files(tmp_path)

        assert found == sorted(
            [
                tmp_path / "packages" / "core" / "tests" / "test_a.py",
                tmp_path / "packages" / "core" / "tests" / "nested" / "test_b.py",
                tmp_path / "examples" / "test_c.py",
            ]
        )

    def test_skips_mutants_and_hidden_directories(self, tmp_path: Path) -> None:
        _write(tmp_path / "packages" / "mutants" / "tests" / "test_a.py", "")
        _write(tmp_path / "packages" / ".hypothesis" / "test_b.py", "")
        _write(tmp_path / "packages" / "core" / "tests" / "test_c.py", "")

        found = _target_test_files(tmp_path)

        assert found == [tmp_path / "packages" / "core" / "tests" / "test_c.py"]

    def test_returns_an_empty_list_when_neither_root_exists(self, tmp_path: Path) -> None:
        assert _target_test_files(tmp_path) == []


class TestFindLargeFixtureTests:
    def test_a_range_10_000_loop_directly_in_the_test_is_detected(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_deep() -> None:\n    for _ in range(10_000):\n        pass\n",
        )

        hits = find_large_fixture_tests(tmp_path)

        assert hits == [
            DeepFixtureHit(
                test_id="packages/core/tests/test_a.py::test_deep", line=1, has_marker=False
            )
        ]

    def test_a_range_50_000_loop_is_detected_too(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_deep() -> None:\n    for _ in range(50_000):\n        pass\n",
        )

        assert [hit.test_id for hit in find_large_fixture_tests(tmp_path)] == [
            "packages/core/tests/test_a.py::test_deep"
        ]

    def test_a_range_below_the_threshold_is_not_detected(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_shallow() -> None:\n    for _ in range(9_999):\n        pass\n",
        )

        assert find_large_fixture_tests(tmp_path) == []

    def test_a_known_chain_builder_call_with_a_literal_10_000_depth_is_detected(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def _chain(depth):\n    return depth\n\n\n"
            "def test_deep() -> None:\n    node = _chain(10_000)\n    assert node\n",
        )

        assert [hit.test_id for hit in find_large_fixture_tests(tmp_path)] == [
            "packages/core/tests/test_a.py::test_deep"
        ]

    def test_a_self_dot_chain_call_is_detected_the_same_way(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "class TestX:\n"
            "    def _chain(self, depth):\n        return depth\n\n"
            "    def test_deep(self) -> None:\n        node = self._chain(10_000)\n"
            "        assert node\n",
        )

        assert [hit.test_id for hit in find_large_fixture_tests(tmp_path)] == [
            "packages/core/tests/test_a.py::TestX.test_deep"
        ]

    def test_a_nest_lists_builder_call_is_detected(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def _nest_lists(depth, payload):\n    return payload\n\n\n"
            "def test_deep() -> None:\n    node = _nest_lists(10_000, 0)\n    assert node == 0\n",
        )

        assert [hit.test_id for hit in find_large_fixture_tests(tmp_path)] == [
            "packages/core/tests/test_a.py::test_deep"
        ]

    def test_a_differently_named_10_000_deep_helper_is_not_detected(self, tmp_path: Path) -> None:
        """Design boundary, not a gap this script tries to close: only the known builder names
        (`chain`/`deep_chain`/`nest_lists`) and a raw `range(10_000|50_000)` loop are recognised --
        mirrors the TS reference implementation's own named-builder-or-raw-loop scope."""
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def _build_tree(depth):\n    return depth\n\n\n"
            "def test_deep() -> None:\n    node = _build_tree(10_000)\n    assert node\n",
        )

        assert find_large_fixture_tests(tmp_path) == []

    def test_a_large_fixture_built_inside_a_nested_helper_def_is_not_chased(
        self, tmp_path: Path
    ) -> None:
        """A large fixture built inside a `def` nested *inside* the test body is attributed to
        that inner call site, never chased into -- this codebase always defines its chain/nest_
        lists helpers at module or class level, never nested inside the test itself."""
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_deep() -> None:\n"
            "    def _inner():\n        for _ in range(10_000):\n            pass\n"
            "    _inner()\n",
        )

        assert find_large_fixture_tests(tmp_path) == []

    def test_an_existing_pytest_mark_timeout_decorator_is_recognised_as_already_marked(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n"
            "@pytest.mark.timeout(0.5)\n"
            "def test_deep() -> None:\n    for _ in range(10_000):\n        pass\n",
        )

        (hit,) = find_large_fixture_tests(tmp_path)
        assert hit.has_marker is True

    def test_an_unrelated_decorator_does_not_count_as_a_timeout_marker(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n"
            '@pytest.mark.parametrize("x", [1])\n'
            "def test_deep(x) -> None:\n    for _ in range(10_000):\n        pass\n",
        )

        (hit,) = find_large_fixture_tests(tmp_path)
        assert hit.has_marker is False

    def test_a_non_test_function_building_a_large_fixture_is_ignored(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def helper_not_a_test() -> None:\n    for _ in range(10_000):\n        pass\n",
        )

        assert find_large_fixture_tests(tmp_path) == []


class TestCheck:
    def test_reports_an_unmarked_hit_as_a_violation_and_never_flags_an_allowlisted_one(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_deep() -> None:\n    for _ in range(10_000):\n        pass\n",
        )
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_b.py",
            "def test_also_deep() -> None:\n    for _ in range(10_000):\n        pass\n",
        )

        result = check(
            tmp_path, {"packages/core/tests/test_b.py::test_also_deep": "reasoned exception"}
        )

        assert [hit.test_id for hit in result.violations] == [
            "packages/core/tests/test_a.py::test_deep"
        ]
        assert result.stale_allowlist_entries == ()

    def test_flags_an_allowlist_entry_whose_test_is_no_longer_a_large_fixture_test_as_stale(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_x() -> None:\n    pass\n",
        )

        result = check(tmp_path, {"packages/core/tests/test_a.py::test_x": "no longer needed"})

        assert result.violations == ()
        assert result.stale_allowlist_entries == ("packages/core/tests/test_a.py::test_x",)

    def test_a_marker_already_present_needs_no_allowlist_entry(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "import pytest\n\n\n"
            "@pytest.mark.timeout(0.5)\n"
            "def test_deep() -> None:\n    for _ in range(10_000):\n        pass\n",
        )

        result = check(tmp_path, {})

        assert result.violations == ()
        assert result.stale_allowlist_entries == ()

    def test_is_clean_when_nothing_matches_and_nothing_is_allowlisted(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "tests" / "test_a.py",
            "def test_x() -> None:\n    pass\n",
        )

        result = check(tmp_path, {})

        assert result.violations == ()
        assert result.stale_allowlist_entries == ()
