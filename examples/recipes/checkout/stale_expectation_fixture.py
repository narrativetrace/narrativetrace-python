# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The failing checkout test documentation/recipes/why-did-this-test-fail.md is read through. It
fails on an assertion, by design, which is why it is a fixture (not collected as a ``test_*``
module): ``recipe_artifacts.py`` runs it in its own pytest process and records what the run
reported.

Nothing here says which side is wrong -- that is the reader's exercise, and the narrative the run
writes is what settles it. Do not add a comment that gives it away.
"""

from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifact names the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_the_customer_gets_an_order_id_for_their_keyboards(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    inventory = trace_object(InventoryService("SKU-KB", 5), narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(OrderRepository(), narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")

    assert order_id == "ORD-C-1234-SKU-KB-1"
