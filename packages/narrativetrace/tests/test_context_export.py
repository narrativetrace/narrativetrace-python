# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the request-context export normalizer (adversarial-audit mirror, F6)."""

from __future__ import annotations

from narrativetrace.context_export import MAX_LENGTH, export


class TestExport:
    def test_an_ordinary_value_is_unchanged(self) -> None:
        assert export("/orders/42") == "/orders/42"

    def test_a_newline_is_escaped(self) -> None:
        assert export("evil\nFAKE LOG LINE") == "evil\\nFAKE LOG LINE"

    def test_a_carriage_return_is_escaped(self) -> None:
        assert export("a\rb") == "a\\rb"

    def test_a_null_byte_is_escaped(self) -> None:
        assert export("a\x00b") == "a\\u0000b"

    def test_an_ansi_escape_is_escaped(self) -> None:
        assert export("a\x1bb") == "a\\u001bb"

    def test_a_c1_control_is_escaped(self) -> None:
        assert export("a\x85b") == "a\\u0085b"

    def test_exactly_at_the_cap_is_not_truncated(self) -> None:
        value = "x" * MAX_LENGTH
        assert export(value) == value

    def test_one_over_the_cap_is_truncated_with_an_ellipsis(self) -> None:
        value = "x" * (MAX_LENGTH + 1)
        result = export(value)
        assert result == "x" * MAX_LENGTH + "…"

    def test_a_million_character_value_is_bounded(self) -> None:
        result = export("x" * 1_000_000)
        assert len(result) == MAX_LENGTH + 1

    def test_escaping_runs_before_capping_so_an_escape_never_straddles_the_boundary(self) -> None:
        # A newline right at the cap boundary must not leave a dangling "\" at position MAX_LENGTH.
        value = ("x" * (MAX_LENGTH - 1)) + "\n" + "y"
        result = export(value)
        assert result == ("x" * (MAX_LENGTH - 1)) + "\\" + "…"
