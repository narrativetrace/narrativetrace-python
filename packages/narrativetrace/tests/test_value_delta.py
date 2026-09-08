# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Intra-trace value deltas.

When the same entity reappears in one trace slightly changed, the later emission renders as a
field-level diff against the in-document reference instead of a second full blob, so the one
changed field is the thing the reader sees.
"""

from __future__ import annotations

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.value_delta import value_delta
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
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

MS = 1_000_000
DINNER_USD = 'Expense(description: "Dinner", amount: 100.0, currency: "USD")'
DINNER_EUR = 'Expense(description: "Dinner", amount: 92.0, currency: "EUR")'
DINNER_GBP = 'Expense(description: "Dinner", amount: 79.0, currency: "GBP")'
DELTA_TO_EUR = '{amount: 100.0→92.0, currency: "USD"→"EUR"}'


def _expense(description: str, amount: float, currency: str) -> ObjectVal:
    return ObjectVal(
        "Expense",
        {
            "description": StringVal(description),
            "amount": FloatVal(amount),
            "currency": StringVal(currency),
        },
    )


def _leaf(cls: str, method: str, value: str, structured: RenderedValue | None) -> TraceNode:
    return TraceNode(
        MethodSignature(cls, method, [ParameterCapture("expense", value, False, structured)]),
        [],
        Returned('"ok"'),
        MS,
    )


def _render(*roots: TraceNode) -> str:
    return MarkdownRenderer().render(TraceTree(list(roots)))


class TestDeltaRendering:
    def test_changed_scalar_fields_render_as_a_delta_against_the_reference(self) -> None:
        result = _render(
            _leaf("TripLedger", "record_expense", DINNER_USD, _expense("Dinner", 100.0, "USD")),
            _leaf("ShareCalculator", "split", DINNER_EUR, _expense("Dinner", 92.0, "EUR")),
        )

        assert f"record_expense**(expense: `‹Dinner›={DINNER_USD}`)" in result
        assert f"split**(expense: `‹Dinner›′{DELTA_TO_EUR}`)" in result

    def test_a_repeated_changed_variant_is_defined_as_a_delta_of_the_reference(self) -> None:
        result = _render(
            _leaf("TripLedger", "record_expense", DINNER_USD, _expense("Dinner", 100.0, "USD")),
            _leaf("ShareCalculator", "split", DINNER_EUR, _expense("Dinner", 92.0, "EUR")),
            _leaf("AuditLog", "append", DINNER_EUR, _expense("Dinner", 92.0, "EUR")),
        )

        assert f"split**(expense: `‹Dinner·2›=‹Dinner›′{DELTA_TO_EUR}`)" in result
        assert "append**(expense: `‹Dinner·2›`)" in result

    def test_every_later_variant_diffs_against_the_same_reference(self) -> None:
        result = _render(
            _leaf("TripLedger", "record_expense", DINNER_USD, _expense("Dinner", 100.0, "USD")),
            _leaf("ShareCalculator", "split", DINNER_EUR, _expense("Dinner", 92.0, "EUR")),
            _leaf("Reporter", "report", DINNER_GBP, _expense("Dinner", 79.0, "GBP")),
        )

        assert f"split**(expense: `‹Dinner›′{DELTA_TO_EUR}`)" in result
        assert 'report**(expense: `‹Dinner›′{amount: 100.0→79.0, currency: "USD"→"GBP"}`)' in result

    def test_a_delta_renders_on_a_return_value_too(self) -> None:
        result = _render(
            TraceNode(
                MethodSignature("TripLedger", "record_expense", []),
                [],
                Returned(DINNER_USD, _expense("Dinner", 100.0, "USD")),
                MS,
            ),
            TraceNode(
                MethodSignature("ShareCalculator", "normalize", []),
                [],
                Returned(DINNER_EUR, _expense("Dinner", 92.0, "EUR")),
                MS,
            ),
        )

        assert f"record_expense**() → `‹Dinner›={DINNER_USD}`" in result
        assert f"normalize**() → `‹Dinner›′{DELTA_TO_EUR}`" in result

    def test_a_contained_reference_and_its_delta_share_one_label(self) -> None:
        container = TraceNode(
            MethodSignature("TripLedger", "expenses_of", []), [], Returned(f"[{DINNER_USD}]"), MS
        )

        result = _render(
            _leaf("TripLedger", "record_expense", DINNER_USD, _expense("Dinner", 100.0, "USD")),
            container,
            _leaf("ShareCalculator", "split", DINNER_EUR, _expense("Dinner", 92.0, "EUR")),
        )

        assert f"record_expense**(expense: `‹Dinner›={DINNER_USD}`)" in result
        assert "expenses_of**() → `[‹Dinner›]`" in result
        assert f"split**(expense: `‹Dinner›′{DELTA_TO_EUR}`)" in result

    def test_a_changed_nested_field_falls_back_to_the_full_render(self) -> None:
        before = 'Trip(name: "Rome week", expenses: [Expense(amount: 10.0)])'
        after = 'Trip(name: "Rome week", expenses: [Expense(amount: 20.0)])'

        def trip(amount: float) -> ObjectVal:
            return ObjectVal(
                "Trip",
                {
                    "name": StringVal("Rome week"),
                    "expenses": ListVal([ObjectVal("Expense", {"amount": FloatVal(amount)})]),
                },
            )

        result = _render(
            _leaf("Planner", "plan", before, trip(10.0)),
            _leaf("Planner", "replan", after, trip(20.0)),
        )

        assert f"plan**(expense: `{before}`)" in result
        assert f"replan**(expense: `{after}`)" in result
        assert "′" not in result
        assert "‹" not in result

    def test_an_unchanged_nested_field_does_not_suppress_the_delta(self) -> None:
        before = 'Expense(description: "Dinner", amount: 100.0, split: Share(payer: "Alice"))'
        after = 'Expense(description: "Dinner", amount: 92.0, split: Share(payer: "Alice"))'

        def with_share(amount: float) -> ObjectVal:
            return ObjectVal(
                "Expense",
                {
                    "description": StringVal("Dinner"),
                    "amount": FloatVal(amount),
                    "split": ObjectVal("Share", {"payer": StringVal("Alice")}),
                },
            )

        result = _render(
            _leaf("TripLedger", "record_expense", before, with_share(100.0)),
            _leaf("ShareCalculator", "split", after, with_share(92.0)),
        )

        assert "split**(expense: `‹Dinner›′{amount: 100.0→92.0}`)" in result

    def test_a_value_without_an_identity_field_is_never_a_delta(self) -> None:
        before = 'Expense(amount: 100.0, currency: "USD", category: "FOOD")'
        after = 'Expense(amount: 92.0, currency: "EUR", category: "FOOD")'

        def anon(amount: float, currency: str) -> ObjectVal:
            return ObjectVal(
                "Expense",
                {
                    "amount": FloatVal(amount),
                    "currency": StringVal(currency),
                    "category": StringVal("FOOD"),
                },
            )

        result = _render(
            _leaf("TripLedger", "record_expense", before, anon(100.0, "USD")),
            _leaf("ShareCalculator", "split", after, anon(92.0, "EUR")),
        )

        assert "′" not in result
        assert "‹" not in result

    def test_the_same_identity_on_a_different_type_is_not_the_same_entity(self) -> None:
        refund = 'Refund(description: "Dinner", amount: 100.0, currency: "USD")'
        refund_value = ObjectVal(
            "Refund",
            {
                "description": StringVal("Dinner"),
                "amount": FloatVal(100.0),
                "currency": StringVal("USD"),
            },
        )

        result = _render(
            _leaf("TripLedger", "record_expense", DINNER_USD, _expense("Dinner", 100.0, "USD")),
            _leaf("TripLedger", "record_refund", refund, refund_value),
        )

        assert "′" not in result
        assert "‹" not in result

    def test_a_redacted_identity_field_never_anchors_a_delta(self) -> None:
        before = 'Expense(description: [REDACTED], amount: 100.0, currency: "USD")'
        after = 'Expense(description: [REDACTED], amount: 92.0, currency: "EUR")'

        result = _render(
            _leaf("A", "record_expense", before, _expense("[REDACTED]", 100.0, "USD")),
            _leaf("B", "split", after, _expense("[REDACTED]", 92.0, "EUR")),
        )

        assert "′" not in result
        assert "‹" not in result

    def test_every_scalar_kind_formats_the_way_the_flat_renderer_prints_it(self) -> None:
        before = 'Order(id: "order-77", count: 1, active: true, note: null, at: 1577836800000)'
        after = 'Order(id: "order-77", count: 2, active: false, note: "rush", at: 1577923200000)'

        def order(count: int, active: bool, note: RenderedValue, millis: int) -> ObjectVal:
            return ObjectVal(
                "Order",
                {
                    "id": StringVal("order-77"),
                    "count": IntVal(count),
                    "active": BoolVal(active),
                    "note": note,
                    "at": InstantVal(millis),
                },
            )

        result = _render(
            _leaf("Warehouse", "receive", before, order(1, True, NullVal(), 1_577_836_800_000)),
            _leaf(
                "Warehouse", "ship", after, order(2, False, StringVal("rush"), 1_577_923_200_000)
            ),
        )

        assert (
            "ship**(expense: `‹order-77›′{count: 1→2, active: true→false, "
            'note: null→"rush", at: 1577836800000→1577923200000}`)'
        ) in result


class TestValueDeltaHelper:
    def test_an_unchanged_pair_has_no_delta(self) -> None:
        assert (
            value_delta(_expense("Dinner", 100.0, "USD"), _expense("Dinner", 100.0, "USD")) is None
        )

    def test_a_different_type_name_has_no_delta(self) -> None:
        other = ObjectVal("Refund", _expense("Dinner", 92.0, "EUR").fields)

        assert value_delta(_expense("Dinner", 100.0, "USD"), other) is None

    def test_an_added_field_is_never_silently_dropped(self) -> None:
        richer = ObjectVal(
            "Expense",
            {
                "description": StringVal("Dinner"),
                "amount": FloatVal(92.0),
                "currency": StringVal("EUR"),
                "category": StringVal("FOOD"),
            },
        )

        assert value_delta(_expense("Dinner", 100.0, "USD"), richer) is None

    def test_a_non_object_value_is_never_one_side_of_a_delta(self) -> None:
        assert value_delta(StringVal("Dinner"), _expense("Dinner", 92.0, "EUR")) is None
        assert value_delta(_expense("Dinner", 100.0, "USD"), StringVal("Dinner")) is None

    def test_a_none_side_is_never_a_delta(self) -> None:
        assert value_delta(None, _expense("Dinner", 92.0, "EUR")) is None
        assert value_delta(_expense("Dinner", 100.0, "USD"), None) is None

    def test_a_string_exactly_at_the_scalar_cap_is_not_elided(self) -> None:
        sixty = "x" * 60
        before = ObjectVal("Note", {"title": StringVal("Standup"), "body": StringVal("before")})
        after = ObjectVal("Note", {"title": StringVal("Standup"), "body": StringVal(sixty)})

        assert value_delta(before, after) == f'{{body: "before"→"{sixty}"}}'

    def test_a_string_one_character_past_the_cap_is_elided(self) -> None:
        before = ObjectVal("Note", {"title": StringVal("Standup"), "body": StringVal("before")})
        after = ObjectVal("Note", {"title": StringVal("Standup"), "body": StringVal("x" * 61)})

        assert value_delta(before, after) == f'{{body: "before"→"{"x" * 60}…"}}'

    def test_a_control_character_never_reaches_the_delta_raw(self) -> None:
        before = ObjectVal("Note", {"title": StringVal("Standup"), "body": StringVal("before")})
        after = ObjectVal("Note", {"title": StringVal("Standup"), "body": StringVal("a\nb")})

        assert value_delta(before, after) == '{body: "before"→"a\\nb"}'

    def test_a_changed_nested_list_has_no_delta(self) -> None:
        before = ObjectVal("Cart", {"id": StringVal("c1"), "lines": ListVal([IntVal(7)])})
        after = ObjectVal("Cart", {"id": StringVal("c1"), "lines": ListVal([IntVal(8)])})

        assert value_delta(before, after) is None
