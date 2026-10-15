# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The checkout: reserve the stock, charge the card, save the order -- and release on a decline."""

from __future__ import annotations

from examples.recipes.checkout.domain import Order, PaymentDeclinedError
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService

UNIT_PRICE_CENTS = 3999


class OrderService:
    def __init__(
        self, inventory: InventoryService, payments: PaymentService, orders: OrderRepository
    ) -> None:
        self._inventory = inventory
        self._payments = payments
        self._orders = orders

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        self._inventory.reserve(sku, quantity)
        amount_cents = UNIT_PRICE_CENTS * quantity
        try:
            self._payments.charge(customer_id, amount_cents, card_number)
        except PaymentDeclinedError:
            self._inventory.release(sku, quantity)
            raise
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
