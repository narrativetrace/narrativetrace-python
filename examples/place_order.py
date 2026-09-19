# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``PlaceOrder`` -- the README "problem" section example, run and tested for real
(README.md #the-problem; the same method embedded in every runtime's README and the website's
before/after panels: five collaborators, two success log lines that say nothing about the four
calls between them, one catch that logs and rethrows).

``OrderServiceBefore.place_order`` and ``OrderServiceAfter.place_order`` are the literal
"before"/"after" blocks the README embeds via ``<!-- snippet: examples/place_order.py
region=before -->`` / ``region=after`` -- the only difference between the two methods is the
deleted log lines; everything else (collaborators, call order, exception type) is identical.

``DecliningPaymentService`` and ``run_failing`` are the "after" method's failing path, traced for
real -- the README embeds them via ``region=failing`` as its exception-narrative example
(README.md #an-exception-in-the-trace), the same collaborators and call order, only the payment
collaborator swapped for one that always raises.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, trace_object

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OrderRequest:
    id: str
    sku: str
    qty: int


@dataclass(frozen=True, slots=True)
class Order:
    id: str


class CustomerService:
    """Looks a customer up by id."""

    def find(self, customer_id: str) -> str:
        return customer_id


class CatalogService:
    """Prices a product by SKU."""

    def price(self, sku: str) -> float:
        return 42.0


class InventoryService:
    """Reserves stock for a SKU."""

    def reserve(self, sku: str, qty: int) -> None:
        return None


class PaymentService:
    """Charges an amount and returns a transaction id."""

    def charge(self, amount: float) -> str:
        return "txn-1"


class OrderRepository:
    """Persists a placed order."""

    def save(self, customer: str, payment: str) -> Order:
        return Order(id=f"ORD-{customer}")


@dataclass(frozen=True, slots=True)
class Collaborators:
    """The five collaborators ``place_order`` calls, one per port."""

    customers: CustomerService
    catalog: CatalogService
    inventory: InventoryService
    payments: PaymentService
    orders: OrderRepository


class _OrderServiceBase:
    """Wiring shared by the "before" and "after" services -- only ``place_order`` differs."""

    def __init__(self, collaborators: Collaborators) -> None:
        self._customers = collaborators.customers
        self._catalog = collaborators.catalog
        self._inventory = collaborators.inventory
        self._payments = collaborators.payments
        self._orders = collaborators.orders


class OrderServiceBefore(_OrderServiceBase):
    """Before -- three hand-written log lines carry the story around the business logic."""

    # snippet:begin before
    def place_order(self, req: OrderRequest) -> Order:
        logger.info("Placing order %s", req.id)
        try:
            customer = self._customers.find(req.id)
            price = self._catalog.price(req.sku)
            self._inventory.reserve(req.sku, req.qty)
            payment = self._payments.charge(price)
            order = self._orders.save(customer, payment)
            logger.info("Order succeeded %s", order.id)
            return order
        except Exception:
            logger.exception("Placing order failed %s", req.id)
            raise

    # snippet:end before


class OrderServiceAfter(_OrderServiceBase):
    """After -- the same method, zero log lines; NarrativeTrace captures the narrative."""

    # snippet:begin after
    def place_order(self, req: OrderRequest) -> Order:
        customer = self._customers.find(req.id)
        price = self._catalog.price(req.sku)
        self._inventory.reserve(req.sku, req.qty)
        payment = self._payments.charge(price)
        return self._orders.save(customer, payment)

    # snippet:end after


# snippet:begin failing
class DecliningPaymentService(PaymentService):
    """Always declines -- the failing-path collaborator for the exception-narrative example."""

    def charge(self, amount: float) -> str:
        raise RuntimeError("payment declined")


def run_failing() -> str:
    """Traces :class:`OrderServiceAfter`'s "after" method with the payment collaborator swapped
    for one that always declines, and renders the resulting narrative, exception included."""
    context = ContextVarNarrativeContext()
    collaborators = Collaborators(
        customers=CustomerService(),
        catalog=CatalogService(),
        inventory=InventoryService(),
        payments=trace_object(DecliningPaymentService(), context),
        orders=OrderRepository(),
    )
    service = trace_object(OrderServiceAfter(collaborators), context)
    try:
        service.place_order(OrderRequest(id="C-1234", sku="SKU-KB", qty=2))
    except RuntimeError:
        pass
    return IndentedTextRenderer().render(context.capture_trace())


# snippet:end failing


def write_artifact() -> str:
    """Runs :func:`run_failing` and saves its output under ``build/`` for
    ``scripts/snippet_check.py`` to embed as the README's exception-narrative output block."""
    rendered = run_failing()
    build_dir = Path(__file__).parent / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "place_order_failing.txt").write_text(rendered, encoding="utf-8")
    return rendered


if __name__ == "__main__":
    print(run_failing())
