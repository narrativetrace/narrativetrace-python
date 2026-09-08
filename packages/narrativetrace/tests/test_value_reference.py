# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Content-addressed value deduplication in the Markdown renderer.

A captured value rendered identically more than once is defined with a readable reference on
first emission and referred to by that reference afterwards. Byte equality certifies sameness;
any difference renders in full.
"""

from __future__ import annotations

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.value_reference import ValueReferenceIndex
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.values import ObjectVal, RenderedValue, StringVal

HOTEL = 'Expense(description: "Hotel", amount: 400.00, currency: "EUR")'
MS = 1_000_000


def _leaf(cls: str, method: str, value: str, structured: RenderedValue | None = None) -> TraceNode:
    return TraceNode(
        MethodSignature(cls, method, [ParameterCapture("expense", value, False, structured)]),
        [],
        Returned('"ok"'),
        MS,
    )


def _render(*roots: TraceNode) -> str:
    return MarkdownRenderer().render(TraceTree(list(roots)))


class TestValueReferences:
    def test_repeated_long_value_defines_a_reference_once_and_reuses_it(self) -> None:
        result = _render(
            _leaf("ExpenseValidator", "ensure_valid", HOTEL),
            _leaf("TripLedger", "record_expense", HOTEL),
        )

        assert f"ensure_valid**(expense: `‹v1›={HOTEL}`)" in result
        assert "record_expense**(expense: `‹v1›`)" in result

    def test_label_comes_from_the_identity_field_of_the_structured_value(self) -> None:
        structured = ObjectVal("Expense", {"description": StringVal("Hotel")})

        result = _render(
            _leaf("ExpenseValidator", "ensure_valid", HOTEL, structured),
            _leaf("TripLedger", "record_expense", HOTEL, structured),
        )

        assert f"ensure_valid**(expense: `‹Hotel›={HOTEL}`)" in result
        assert "record_expense**(expense: `‹Hotel›`)" in result

    def test_short_repeated_values_are_never_referenced(self) -> None:
        assert "‹" not in _render(_leaf("A", "m", '"short"'), _leaf("B", "n", '"short"'))

    def test_an_object_without_an_identity_field_falls_back_to_its_type_name(self) -> None:
        structured = ObjectVal("Expense", {"amount": StringVal("400.00")})

        result = _render(_leaf("A", "one", HOTEL, structured), _leaf("B", "two", HOTEL, structured))

        assert "‹Expense›=" in result

    def test_a_redacted_identity_field_is_skipped_for_the_next_candidate(self) -> None:
        structured = ObjectVal(
            "Expense", {"description": StringVal("[REDACTED]"), "title": StringVal("Hotel")}
        )

        result = _render(_leaf("A", "one", HOTEL, structured), _leaf("B", "two", HOTEL, structured))

        assert "‹Hotel›=" in result
        assert "‹[REDACTED]›" not in result

    def test_colliding_identity_labels_are_disambiguated_with_ordinals(self) -> None:
        other = 'Trip(description: "Hotel", nights: 3, city: "Rome city")'

        result = _render(
            _leaf("A", "one", HOTEL, ObjectVal("Expense", {"description": StringVal("Hotel")})),
            _leaf("B", "two", HOTEL, ObjectVal("Expense", {"description": StringVal("Hotel")})),
            _leaf("C", "three", other, ObjectVal("Trip", {"description": StringVal("Hotel")})),
            _leaf("D", "four", other, ObjectVal("Trip", {"description": StringVal("Hotel")})),
        )

        assert "‹Hotel›=" in result
        assert "‹Hotel·2›=" in result

    def test_an_identity_label_longer_than_the_cap_is_elided(self) -> None:
        long_name = "a description far longer than the twenty-four character cap"
        value = f'Expense(description: "{long_name}", amount: 1.00)'
        structured = ObjectVal("Expense", {"description": StringVal(long_name)})

        result = _render(_leaf("A", "one", value, structured), _leaf("B", "two", value, structured))

        assert f"‹{long_name[:24]}…›=" in result

    def test_a_label_exactly_at_the_cap_is_not_elided(self) -> None:
        exact = "x" * 24
        value = f'Expense(description: "{exact}", amount: 1.00, currency: "EUR")'
        structured = ObjectVal("Expense", {"description": StringVal(exact)})

        result = _render(_leaf("A", "one", value, structured), _leaf("B", "two", value, structured))

        assert f"‹{exact}›=" in result

    def test_control_characters_in_an_identity_value_are_sanitized(self) -> None:
        structured = ObjectVal("Expense", {"description": StringVal("Ho\ntel")})

        result = _render(_leaf("A", "one", HOTEL, structured), _leaf("B", "two", HOTEL, structured))

        assert "‹Ho\\ntel›=" in result
        assert "‹Ho\ntel›" not in result

    def test_a_referenced_value_is_replaced_inside_container_values(self) -> None:
        container = TraceNode(
            MethodSignature("TripLedger", "expenses_of", []), [], Returned(f"[{HOTEL}]"), MS
        )

        result = _render(
            _leaf("ExpenseValidator", "ensure_valid", HOTEL),
            _leaf("TripLedger", "record_expense", HOTEL),
            container,
        )

        assert "expenses_of**() → `[‹v1›]`" in result

    def test_containment_inside_another_captured_value_counts_toward_a_reference(self) -> None:
        container = TraceNode(
            MethodSignature("TripLedger", "expenses_of", []), [], Returned(f"[{HOTEL}]"), MS
        )

        result = _render(_leaf("ExpenseValidator", "ensure_valid", HOTEL), container)

        assert f"ensure_valid**(expense: `‹v1›={HOTEL}`)" in result
        assert "expenses_of**() → `[‹v1›]`" in result

    def test_a_value_exactly_at_the_minimum_length_is_referenced(self) -> None:
        exact = "y" * 40

        assert "‹v1›=" in _render(_leaf("A", "one", exact), _leaf("B", "two", exact))

    def test_a_value_one_character_below_the_minimum_is_not_referenced(self) -> None:
        short = "y" * 39

        assert "‹" not in _render(_leaf("A", "one", short), _leaf("B", "two", short))

    def test_a_redacted_parameter_never_enters_the_index(self) -> None:
        secret = 'Card(number: "4111111111111111", holder: "Alice Smith")'
        sig = MethodSignature("Payments", "charge", [ParameterCapture("card", secret, True)])
        node = TraceNode(sig, [], Returned('"ok"'), MS)

        result = _render(node, node)

        assert "card: `[REDACTED]`" in result
        assert "4111111111111111" not in result
        assert "‹" not in result


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): value counting used unbounded native recursion with no
    depth bound or cycle guard -- both a cycle and a pathologically deep chain crashed with an
    uncaught RecursionError. Exercised directly against the index build, not the full renderer,
    since ``MarkdownRenderer.render`` has its own, separately-fixed tree walk."""

    def test_a_self_referential_node_does_not_crash_indexing(self) -> None:
        node = _leaf("Svc", "m", "x")
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        ValueReferenceIndex.build(TraceTree([node]))  # must not raise RecursionError

    def test_a_ten_thousand_deep_chain_does_not_overflow_the_stack(self) -> None:
        node = _leaf("Svc", "leaf", "x")
        for _ in range(10_000):
            node = TraceNode(MethodSignature("Svc", "wrap", []), [node], Returned('"ok"'))
        ValueReferenceIndex.build(TraceTree([node]))  # must not raise RecursionError
