# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the TraceOutcome sealed union."""

from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.values import IntVal


def test_returned_defaults_structured_to_none() -> None:
    outcome = Returned("42")
    assert outcome.rendered_value == "42"
    assert outcome.structured_value is None


def test_returned_carries_structured_value() -> None:
    outcome = Returned("42", IntVal(42))
    assert outcome.structured_value == IntVal(42)


def test_returned_allows_none_for_void() -> None:
    assert Returned(None).rendered_value is None


def test_threw_holds_exception() -> None:
    err = ValueError("boom")
    assert Threw(err).exception is err


def test_variants_are_trace_outcomes() -> None:
    outcomes: list[TraceOutcome] = [Returned("x"), Threw(ValueError()), Incomplete()]
    assert all(isinstance(o, TraceOutcome) for o in outcomes)


def test_pattern_matching() -> None:
    def describe(o: TraceOutcome) -> str:
        match o:
            case Returned(rendered_value=v):
                return f"returned {v}"
            case Threw(exception=e):
                return f"threw {type(e).__name__}"
            case Incomplete():
                return "incomplete"
        return "?"

    assert describe(Returned("1")) == "returned 1"
    assert describe(Threw(KeyError())) == "threw KeyError"
    assert describe(Incomplete()) == "incomplete"
