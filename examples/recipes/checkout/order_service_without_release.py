# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The same checkout with no release path: a declined charge leaves the reservation behind."""

from __future__ import annotations

from examples.recipes.checkout.domain import Order
from examples.recipes.checkout.order_service import UNIT_PRICE_CENTS
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService


class OrderServiceWithoutRelease:
    """Two recipe pages need this code to RUN, not to be described: ``help-me-debug-and-fix-this-
    bug`` (the bug, before its fix) and ``review-a-refactoring-did-behaviour-change`` (the
    refactoring that drops the release call while every test stays green). It is kept beside
    ``OrderService`` rather than reconstructed by a flag, so each page embeds real source and each
    run is a real run.

    Never the implementation to copy: ``OrderService`` is. A trace names the class it was told to
    name, and both are wrapped as ``OrderService``
    (``trace_object(..., class_name="OrderService")``) -- which is exactly what makes one approved
    trace comparable across the two.
    """

    def __init__(
        self, inventory: InventoryService, payments: PaymentService, orders: OrderRepository
    ) -> None:
        self._inventory = inventory
        self._payments = payments
        self._orders = orders

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        self._inventory.reserve(sku, quantity)
        amount_cents = UNIT_PRICE_CENTS * quantity
        self._payments.charge(customer_id, amount_cents, card_number)
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
