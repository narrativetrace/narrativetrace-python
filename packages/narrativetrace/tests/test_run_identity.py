# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for RunIdentity -- a test-suite execution's own id and three-word phrase."""

from __future__ import annotations

import pytest

from narrativetrace.namer import trace_name
from narrativetrace.output.run_identity import RunIdentity


class TestGenerate:
    def test_generate_produces_a_well_formed_hex_id(self) -> None:
        identity = RunIdentity.generate()

        assert len(identity.id) == 32
        assert all(c in "0123456789abcdef" for c in identity.id)

    def test_generate_derives_the_name_from_the_same_tables_as_trace_name(self) -> None:
        identity = RunIdentity.generate()

        assert identity.name == trace_name(identity.id)

    def test_generate_produces_a_three_word_phrase(self) -> None:
        identity = RunIdentity.generate()

        assert len(identity.name.split(" ")) == 3

    def test_two_generations_differ_in_practice(self) -> None:
        first = RunIdentity.generate()
        second = RunIdentity.generate()

        assert first.id != second.id


class TestValidation:
    def test_rejects_empty_id(self) -> None:
        with pytest.raises(ValueError, match="id"):
            RunIdentity("", "bold elk soars")

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            RunIdentity("a" * 32, "")


class TestEquality:
    def test_same_id_always_produces_the_same_name(self) -> None:
        hex_value = "a3f7c1b290de4f8801234567deadbeef"

        one = RunIdentity(hex_value, trace_name(hex_value))
        two = RunIdentity(hex_value, trace_name(hex_value))

        assert one == two
