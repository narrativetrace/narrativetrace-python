# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the RenderedValue structured-value union (data only)."""

import dataclasses

import pytest

from narrativetrace.values import (
    BoolVal,
    FloatVal,
    InstantVal,
    IntVal,
    ListVal,
    NullVal,
    ObjectVal,
    RenderedValue,
    StringVal,
)


def test_variants_are_rendered_values() -> None:
    variants: list[RenderedValue] = [
        StringVal("x"),
        IntVal(1),
        FloatVal(1.5),
        BoolVal(True),
        InstantVal(1000),
        ObjectVal("Order", {"id": IntVal(7)}),
        ListVal([IntVal(1), IntVal(2)]),
        NullVal(),
    ]
    assert all(isinstance(v, RenderedValue) for v in variants)


def test_values_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        StringVal("x").value = "y"  # type: ignore[misc]


def test_equality_by_value() -> None:
    assert ObjectVal("Order", {"id": IntVal(7)}) == ObjectVal("Order", {"id": IntVal(7)})
    an_int: RenderedValue = IntVal(1)
    a_float: RenderedValue = FloatVal(1.0)
    assert an_int != a_float


def test_pattern_matching_dispatch() -> None:
    def kind(v: RenderedValue) -> str:
        match v:
            case IntVal():
                return "int"
            case NullVal():
                return "null"
            case _:
                return "other"

    assert kind(IntVal(1)) == "int"
    assert kind(NullVal()) == "null"
    assert kind(StringVal("x")) == "other"
