# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The checkout with the two slow steps off the caller's thread, for
documentation/recipes/follow-a-flow-across-threads.md."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any

from examples.recipes.checkout.domain import Order, PaymentDeclinedError
from examples.recipes.checkout.fraud import RuleBasedFraudCheck
from examples.recipes.checkout.order_service import UNIT_PRICE_CENTS
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ForkJoinGroup, NarrativeContext


class ParallelCheckout:
    """Reserves the stock and runs the fraud check on an executor, waits for both, then charges
    and saves.

    A task handed to an executor runs on a thread that knows nothing about the caller's trace, so
    the trace has to be handed over with it: ``group.wrap`` takes a snapshot at submission time,
    the worker activates it, and ``group.merge()`` grafts what the worker recorded back under the
    span that launched it. Every forked task must be wrapped and ``merge()`` must run after they
    finish, or the children stay detached from the caller's trace.
    """

    def __init__(
        self,
        context: NarrativeContext,
        inventory: InventoryService,
        fraud: RuleBasedFraudCheck,
        payments: PaymentService,
        orders: OrderRepository,
        workers: ThreadPoolExecutor,
    ) -> None:
        self._context = context
        self._inventory = inventory
        self._fraud = fraud
        self._payments = payments
        self._orders = orders
        self._workers = workers

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        amount_cents = UNIT_PRICE_CENTS * quantity

        group = ForkJoinGroup.create(self._context)
        reserved = self._workers.submit(group.wrap(lambda: self._inventory.reserve(sku, quantity)))
        approved = self._workers.submit(
            group.wrap(lambda: self._fraud.approve(customer_id, amount_cents))
        )
        tasks: list[Future[Any]] = [reserved, approved]
        wait(tasks)  # the merge may only run after both are done
        group.merge()

        reserved.result()  # a task's own failure is the caller's, raised here
        if not approved.result():
            self._inventory.release(sku, quantity)
            raise PaymentDeclinedError("the fraud check refused the order")
        self._payments.charge(customer_id, amount_cents, card_number)
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
