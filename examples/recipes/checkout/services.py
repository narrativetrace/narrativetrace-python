# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The checkout's three collaborators, in memory, so a scenario needs no database or gateway."""

from __future__ import annotations

from examples.recipes.checkout.domain import Order, PaymentDeclinedError


class InventoryService:
    """The stock the checkout reserves before it charges, and releases when it must not."""

    def __init__(self, sku: str, units: int) -> None:
        self._units_by_sku = {sku: units}

    def reserve(self, sku: str, quantity: int) -> None:
        available = self.available_units(sku)
        if available < quantity:
            raise ValueError(f"not enough stock for {sku}")
        self._units_by_sku[sku] = available - quantity

    def release(self, sku: str, quantity: int) -> None:
        self._units_by_sku[sku] = self.available_units(sku) + quantity

    def available_units(self, sku: str) -> int:
        return self._units_by_sku.get(sku, 0)


class PaymentService:
    """A card gateway stub: it declines the one test card gateways document as declining.

    The parameter is named ``card``, not ``card_number``, on purpose: the name deny-list does not
    know it, so the recipes show a number hidden by its value.
    """

    DECLINING_CARD = "4000000000000002"
    """The card every gateway's test suite declines. Luhn-valid, like a real one."""

    def charge(self, customer_id: str, amount_cents: int, card: str) -> str:
        if card == self.DECLINING_CARD:
            raise PaymentDeclinedError("card declined by the issuer")
        return f"PAY-{customer_id}-{amount_cents}"


class OrderRepository:
    """Saved orders in a list, so a test can assert on what was saved."""

    def __init__(self) -> None:
        self._saved: list[Order] = []

    def save(self, order: Order) -> None:
        self._saved.append(order)

    def saved(self) -> list[Order]:
        """Every order saved so far, in the order they were saved."""
        return list(self._saved)
