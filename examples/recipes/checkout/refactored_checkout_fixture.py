# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The test documentation/recipes/review-a-refactoring-did-behaviour-change.md pins: a declined card
must save no order. It passes before and after the refactoring -- which is the whole point of the
page -- so only the approved structure can object.

A fixture because ``recipe_artifacts.py`` runs it twice under approval mode, once per version of the
checkout, and reads the verdicts. ``NARRATIVETRACE_RECIPE_REFACTORED`` picks the version: in your
project the refactoring is an edit to one file and this switch does not exist.
"""

import os

import pytest

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.env import REFACTORED_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.order_service_without_release import OrderServiceWithoutRelease
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_a_declined_card_saves_no_order(narrative_trace: ContextVarNarrativeContext) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    service_class = OrderServiceWithoutRelease if os.environ.get(REFACTORED_ENV) else OrderService
    checkout = trace_object(
        service_class(inventory, payments, orders), narrative_trace, class_name="OrderService"
    )

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
