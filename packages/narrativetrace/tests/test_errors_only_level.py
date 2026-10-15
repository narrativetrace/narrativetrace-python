# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The tracing level changes what a real traced flow captures: in the checkout recipe's flow an
errors-only run keeps nothing when every call succeeds and only the failing path when one throws,
while the default level keeps the whole flow."""

from __future__ import annotations

import pytest

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel
from narrativetrace.nodes import TraceNode
from narrativetrace.trace_object import trace_object


class Inventory:
    def reserve(self, sku: str) -> bool:
        return True


class Payment:
    def __init__(self, declines: bool) -> None:
        self._declines = declines

    def charge(self, amount_cents: int) -> str:
        if self._declines:
            raise ValueError("card declined")
        return "paid"


class Orders:
    def save(self, order_id: str) -> str:
        return order_id


class Checkout:
    def __init__(self, context: ContextVarNarrativeContext, declines: bool) -> None:
        self._inventory = trace_object(Inventory(), context)
        self._payment = trace_object(Payment(declines), context)
        self._orders = trace_object(Orders(), context)

    def place_order(self, sku: str) -> str:
        self._inventory.reserve(sku)
        self._payment.charge(1999)
        return self._orders.save("ORD-1")


def _run(level: TracingLevel, declines: bool) -> list[TraceNode]:
    context = ContextVarNarrativeContext(NarrativeTraceConfig(level))
    checkout = trace_object(Checkout(context, declines), context)
    if declines:
        with pytest.raises(ValueError, match=r"\Acard declined\Z"):
            checkout.place_order("sku-1")
    else:
        checkout.place_order("sku-1")
    return context.capture_trace().roots


def _calls(nodes: list[TraceNode]) -> list[str]:
    return [
        f"{node.signature.class_name}.{node.signature.method_name}"
        for root in nodes
        for node in [root, *root.children]
    ]


class TestErrorsOnlyLevel:
    def test_a_flow_where_every_call_succeeds_captures_nothing(self) -> None:
        assert _run(TracingLevel.ERRORS, declines=False) == []

    def test_a_failing_flow_keeps_the_failing_path_from_its_root(self) -> None:
        calls = _calls(_run(TracingLevel.ERRORS, declines=True))

        assert "Checkout.place_order" in calls
        assert "Payment.charge" in calls

    def test_the_default_level_captures_the_whole_flow(self) -> None:
        assert _calls(_run(TracingLevel.DETAIL, declines=False)) == [
            "Checkout.place_order",
            "Inventory.reserve",
            "Payment.charge",
            "Orders.save",
        ]

    def test_off_captures_nothing_even_when_the_flow_fails(self) -> None:
        assert _run(TracingLevel.OFF, declines=True) == []
