# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-207: a negative renderer limit is never trusted -- it behaves exactly as 0, and the renderer
says so once, when it is constructed. Unclamped, ``items[:-1]`` / ``safe[:-1]`` silently dropped
the LAST item or character instead of capping."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from narrativetrace.rendering import ValueRenderer


class Bean:
    def __init__(self) -> None:
        self.a = "one"
        self.b = "two"
        self.c = "three"


def _same_as_zero(
    capsys: pytest.CaptureFixture[str], name: str, make: Callable[[int], ValueRenderer]
) -> None:
    negative = make(-1)
    zero = make(0)
    capsys.readouterr()
    for value in ("abcdef", [1, 2, 3], {"k": 1, "j": 2}, {1, 2, 3}, Bean()):
        assert negative.render(value) == zero.render(value), (name, value)
        assert repr(negative.render_structured(value)) == repr(zero.render_structured(value)), (
            name,
            value,
        )


class TestNegativeLimitBehavesAsZero:
    def test_string_cap(self, capsys: pytest.CaptureFixture[str]) -> None:
        _same_as_zero(capsys, "max_string_length", lambda n: ValueRenderer(max_string_length=n))

    def test_element_cap(self, capsys: pytest.CaptureFixture[str]) -> None:
        _same_as_zero(
            capsys, "max_collection_items", lambda n: ValueRenderer(max_collection_items=n)
        )

    def test_field_cap(self, capsys: pytest.CaptureFixture[str]) -> None:
        _same_as_zero(capsys, "max_object_fields", lambda n: ValueRenderer(max_object_fields=n))


class TestClampIsReportedOnce:
    def test_one_line_names_every_clamped_limit(self, capsys: pytest.CaptureFixture[str]) -> None:
        ValueRenderer(max_string_length=-1, max_collection_items=-2, max_object_fields=-3)
        err = capsys.readouterr().err
        assert err == (
            "narrative-trace: renderer limits below zero are clamped to 0: "
            "max_string_length=-1, max_collection_items=-2, max_object_fields=-3\n"
        )

    def test_only_the_negative_limit_is_named(self, capsys: pytest.CaptureFixture[str]) -> None:
        ValueRenderer(max_collection_items=-5)
        assert capsys.readouterr().err == (
            "narrative-trace: renderer limits below zero are clamped to 0: "
            "max_collection_items=-5\n"
        )

    def test_valid_limits_say_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        ValueRenderer(max_string_length=0, max_collection_items=3, max_object_fields=1)
        assert capsys.readouterr().err == ""

    def test_the_stored_limit_is_zero(self) -> None:
        r = ValueRenderer(max_string_length=-1, max_collection_items=-1, max_object_fields=-1)
        assert (r.max_string_length, r.max_collection_items, r.max_object_fields) == (0, 0, 0)
