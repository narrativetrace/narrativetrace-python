# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The reproduction documentation/recipes/help-me-debug-and-fix-this-bug.md is written around: a
declined card must leave the stock as it found it.

The second test is the same reproduction against the checkout as it stood before the fix
(``OrderServiceWithoutRelease``), so the page's "before" trace comes from a real failing run rather
than from prose. It FAILS by design, which is why this module is a fixture (not collected as a
``test_*`` module): ``recipe_artifacts.py`` runs it in its own pytest process and records what the
run reported.

Both tests adopt the same fixed trace id, so the two artifacts a reader compares differ only where
the code differs.
"""

import pytest

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.order_service_without_release import OrderServiceWithoutRelease
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_the_stock_is_released_when_the_card_is_declined(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
    assert stock.available_units("SKU-KB") == 5


def test_the_stock_is_released_when_the_card_is_declined_before_the_fix(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(
        OrderServiceWithoutRelease(inventory, payments, orders),
        narrative_trace,
        class_name="OrderService",
    )

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
    assert stock.available_units("SKU-KB") == 5
