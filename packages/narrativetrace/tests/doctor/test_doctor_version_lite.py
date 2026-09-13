# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import pytest

from narrativetrace.doctor.version_lite import dependency_specifier, parse_version, satisfies


class TestParseVersion:
    def test_full_triple(self) -> None:
        assert parse_version("3.12.4") == (3, 12, 4)

    def test_missing_parts_default_to_zero(self) -> None:
        assert parse_version("3.12") == (3, 12, 0)
        assert parse_version("3") == (3, 0, 0)

    def test_unparseable_returns_none(self) -> None:
        assert parse_version("not-a-version") is None

    def test_leading_whitespace_is_trimmed(self) -> None:
        assert parse_version("  3.12.4  ") == (3, 12, 4)


class TestSatisfies:
    @pytest.mark.parametrize(
        ("version", "specifier"),
        [
            ("3.12.4", ">=3.12"),
            ("3.12.0", ">=3.12"),
            ("9.1.1", ">=8"),
            ("8.0.0", ">=8"),
            ("1.2.3", "==1.2.3"),
            ("1.2.3", "!=1.2.4"),
            ("1.2.3", ">=1,<2"),
        ],
    )
    def test_satisfied(self, version: str, specifier: str) -> None:
        assert satisfies(version, specifier) is True

    @pytest.mark.parametrize(
        ("version", "specifier"),
        [
            ("3.11.9", ">=3.12"),
            ("7.9.9", ">=8"),
            ("1.2.4", "==1.2.3"),
            ("1.2.4", "!=1.2.4"),
            ("2.0.0", ">=1,<2"),
        ],
    )
    def test_not_satisfied(self, version: str, specifier: str) -> None:
        assert satisfies(version, specifier) is False

    def test_unparseable_version_is_a_mismatch_not_a_throw(self) -> None:
        assert satisfies("not-a-version", ">=3.12") is False

    def test_unparseable_specifier_is_a_mismatch_not_a_throw(self) -> None:
        assert satisfies("3.12.4", "garbage") is False

    def test_empty_specifier_is_a_mismatch(self) -> None:
        assert satisfies("3.12.4", "") is False


class TestDependencySpecifier:
    def test_finds_matching_dependency(self) -> None:
        assert dependency_specifier(("pytest>=8",), "pytest") == ">=8"

    def test_absent_dependency_returns_none(self) -> None:
        assert dependency_specifier(("narrativetrace",), "pytest") is None

    def test_bare_dependency_with_no_specifier_returns_none(self) -> None:
        assert dependency_specifier(("narrativetrace",), "narrativetrace") is None

    def test_does_not_match_a_sibling_with_a_shared_prefix(self) -> None:
        """`pytest` must not match `pytest-asyncio` — a boundary check, not a bare `startswith`."""
        assert dependency_specifier(("pytest-asyncio>=1",), "pytest") is None

    def test_strips_an_environment_marker(self) -> None:
        assert dependency_specifier(("pytest>=8; python_version >= '3.10'",), "pytest") == ">=8"
