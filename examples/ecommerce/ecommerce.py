# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""E-commerce order flow — the flagship example, a guided tour in six scenarios.

The domain is a small shop: ``OrderService.place_order`` resolves the customer, prices the line,
reserves stock, quotes discount and shipping **concurrently** on a thread pool (a fork-join group
whose children merge back under the order span), charges the card, and launches the
order-confirmed notification **fire-and-forget** on the same pool. That launched notification is
where the second concurrency flavor lives: ``AsyncNotificationService.notify_order_confirmed`` is
a genuine ``async def`` — a :class:`~narrativetrace.ForkJoinGroup` created *from inside* the
running coroutine fans email confirmation and loyalty-points credit out over ``asyncio.gather``
and merges them back under it. One trace, two concurrency mechanisms: threads for the pricing
quotes, asyncio for the notification fan-out — both nest correctly under the spans that started
them. The services are plain classes with no logging calls; wrapping each one with
:func:`~narrativetrace.trace_object` is all it takes for the narrative to appear.

Run it::

    python -m examples.ecommerce            # live → ← !! stream, then the renderings
    python -m examples.ecommerce --classic  # the same run as ordinary timestamped log lines
    python -m examples.demo --example ecommerce   # paced, colorized, with wiring notes

What you will see:

1. A successful order that fans out into background work, on threads and on asyncio.
2. A payment failure where the trace exposes an inventory-release bug.
3. A flaky external dependency that succeeds once and then fails.
4. An unknown customer and 5. an out-of-stock request — the failure branches.
6. Explicit async capture: a worker thread hands back its own trace.

Reading order: :func:`scenarios` → :class:`OrderService` (the orchestration that produces the
interesting traces) → :class:`AsyncNotificationService` (the asyncio fan-out) →
:func:`build_shop` (how the trace context is wired in).
"""

from __future__ import annotations

import asyncio
import itertools
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

from examples.tour import MARKDOWN, MERMAID, PROSE, TREE, Scenario, narrated_run, walk
from narrativetrace import (
    FireAndForgetGroup,
    ForkJoinGroup,
    NarrativeContext,
    TraceTree,
    narrated,
    not_traced,
    on_error,
    trace_object,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO


# --------------------------------------------------------------------------- #
# Domain values and failures                                                  #
# --------------------------------------------------------------------------- #
class CustomerTier(Enum):
    GOLD = "GOLD"
    STANDARD = "STANDARD"


@dataclass(frozen=True, slots=True)
class Customer:
    id: str
    name: str
    tier: CustomerTier


@dataclass(frozen=True, slots=True)
class Reservation:
    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class Discount:
    percent: int


@dataclass(frozen=True, slots=True)
class ShippingEstimate:
    days: int
    cost: float


@dataclass(frozen=True, slots=True)
class PaymentConfirmation:
    transaction_id: str
    amount: float


@dataclass(frozen=True, slots=True)
class OrderResult:
    order_id: str
    transaction_id: str
    total: float
    quantity: int


class UnknownCustomerError(LookupError):
    """The customer id is not on file."""


class OutOfStockError(RuntimeError):
    """The requested quantity exceeds the available stock."""


class PaymentDeclinedError(RuntimeError):
    """The payment provider declined the charge."""


class ExternalServiceError(RuntimeError):
    """A third-party service could not be reached."""


# --------------------------------------------------------------------------- #
# Collaborating services — plain classes, in-memory adapters                  #
# --------------------------------------------------------------------------- #
class CustomerService:
    """Looks customers up by id."""

    _customers: ClassVar[dict[str, Customer]] = {
        "C-1234": Customer("C-1234", "Alice Johnson", CustomerTier.GOLD),
        "C-5678": Customer("C-5678", "Bob Smith", CustomerTier.STANDARD),
        "C-BROKE": Customer("C-BROKE", "Charlie Broke", CustomerTier.STANDARD),
    }

    @on_error(UnknownCustomerError, "Customer {customer_id} not found")
    def find_customer(self, customer_id: str) -> Customer:
        try:
            return self._customers[customer_id]
        except KeyError:
            raise UnknownCustomerError(f"Customer not found: {customer_id}") from None


class ProductCatalogService:
    """Prices products by SKU."""

    _prices: ClassVar[dict[str, float]] = {
        "SKU-MECHANICAL-KB": 89.99,
        "SKU-MOUSE-PAD": 24.99,
        "SKU-USB-HUB": 39.99,
    }

    def lookup_price(self, product_id: str) -> float:
        try:
            return self._prices[product_id]
        except KeyError:
            raise LookupError(f"Product not found: {product_id}") from None


class InventoryService:
    """Reserves and releases stock."""

    def __init__(self) -> None:
        self._stock = {"SKU-MECHANICAL-KB": 150, "SKU-MOUSE-PAD": 500, "SKU-USB-HUB": 75}

    @on_error(OutOfStockError, "Insufficient stock for {product_id}, requested {quantity}")
    def reserve(self, product_id: str, quantity: int) -> Reservation:
        available = self._stock.get(product_id, 0)
        if available < quantity:
            raise OutOfStockError(
                f"Insufficient stock for {product_id}: requested {quantity}, available {available}"
            )
        self._stock[product_id] = available - quantity
        return Reservation(product_id, quantity)

    def release(self, product_id: str, quantity: int) -> None:
        self._stock[product_id] = self._stock.get(product_id, 0) + quantity


class DiscountService:
    """Quotes the customer's discount (a remote pricing rule in a real shop)."""

    def calculate_discount(self, customer_id: str, product_id: str) -> Discount:
        return Discount(10 if customer_id == "C-1234" else 0)


class ShippingEstimateService:
    """Quotes delivery time and cost (a carrier API in a real shop)."""

    def estimate(self, product_id: str, quantity: int) -> ShippingEstimate:
        return ShippingEstimate(days=2 if quantity < 10 else 5, cost=4.99)


class PaymentService:
    """Charges a card token; the token never reaches the trace."""

    _declined = frozenset({"C-BROKE"})

    def __init__(self) -> None:
        self._transactions = itertools.count(1)

    @on_error(
        PaymentDeclinedError, "Payment declined for customer {customer_id}, amount was {amount}"
    )
    @not_traced("card_token")
    def charge(self, customer_id: str, amount: float, card_token: str) -> PaymentConfirmation:
        if customer_id in self._declined:
            raise PaymentDeclinedError(f"Payment declined for customer {customer_id}")
        return PaymentConfirmation(f"TXN-{next(self._transactions):05d}", amount)


class NotificationService:
    """Sends the order-confirmed message (an email or push provider in a real shop)."""

    @on_error(
        ExternalServiceError, "Failed to notify customer {customer_id} about order {order_id}"
    )
    def notify_order_placed(self, customer_id: str, order_id: str) -> bool:
        return True


class FlakyNotificationService:
    """A decorator over a real notifier that starts failing from ``fail_on_call`` onwards."""

    def __init__(self, delegate: NotificationService, fail_on_call: int) -> None:
        self._delegate = delegate
        self._fail_on_call = fail_on_call
        self._calls = 0

    @on_error(
        ExternalServiceError, "Failed to notify customer {customer_id} about order {order_id}"
    )
    def notify_order_placed(self, customer_id: str, order_id: str) -> bool:
        self._calls += 1
        if self._calls >= self._fail_on_call:
            raise ExternalServiceError(
                f"External notification service unavailable (call #{self._calls})"
            )
        return self._delegate.notify_order_placed(customer_id, order_id)


class EmailService:
    """Sends transactional email (an ESP API in a real shop)."""

    async def send_confirmation(self, customer_id: str, order_id: str) -> bool:
        await asyncio.sleep(0)
        return True


class LoyaltyService:
    """Credits loyalty points for a completed order (a rewards API in a real shop)."""

    async def award_points(self, customer_id: str, order_id: str) -> int:
        await asyncio.sleep(0)
        return 10


class AsyncNotificationService:
    """Confirms an order by email and loyalty credit — the asyncio half of the shop's concurrency.

    ``notify_order_confirmed`` is a genuine ``async def``, traced like any other method. Its
    :class:`~narrativetrace.ForkJoinGroup` is created *from inside* the running coroutine —
    ``ForkJoinGroup.create`` reads the async scoped parent, not the active stack — so the two
    children ``asyncio.gather`` fans out land under this span once merged. Threads carry the
    order's pricing quotes (:meth:`OrderService._quote_in_parallel`); asyncio carries this one.
    """

    def __init__(
        self, context: NarrativeContext, email: EmailService, loyalty: LoyaltyService
    ) -> None:
        self._context = context
        self._email = email
        self._loyalty = loyalty

    @narrated("Confirming order {order_id} to customer {customer_id} by email and loyalty credit")
    async def notify_order_confirmed(self, customer_id: str, order_id: str) -> tuple[bool, int]:
        """Fork-join over asyncio: both children merge back under this async span, not as roots."""
        group = ForkJoinGroup.create(self._context)
        email_sent, points = await asyncio.gather(
            group.run_async(lambda: self._email.send_confirmation(customer_id, order_id)),
            group.run_async(lambda: self._loyalty.award_points(customer_id, order_id)),
        )
        group.merge()
        return email_sent, points


# --------------------------------------------------------------------------- #
# Orchestration                                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Collaborators:
    """The services an order needs, one per port, plus the pool background work runs on."""

    customers: CustomerService
    catalog: ProductCatalogService
    inventory: InventoryService
    discounts: DiscountService
    shipping: ShippingEstimateService
    payments: PaymentService
    notifications: AsyncNotificationService
    executor: ThreadPoolExecutor


class OrderService:
    """Coordinates the collaborators for one order — the trace you came to read."""

    def __init__(self, context: NarrativeContext, collaborators: Collaborators) -> None:
        self._context = context
        self._ports = collaborators
        self._orders = itertools.count(1)

    @narrated("Placing order of {quantity} {product_id} for customer {customer_id}")
    def place_order(self, customer_id: str, product_id: str, quantity: int) -> OrderResult:
        ports = self._ports
        customer = ports.customers.find_customer(customer_id)
        unit_price = ports.catalog.lookup_price(product_id)
        ports.inventory.reserve(product_id, quantity)
        discount, shipping = self._quote_in_parallel(customer_id, product_id, quantity)
        total = round(unit_price * quantity * (100 - discount.percent) / 100 + shipping.cost, 2)
        payment = ports.payments.charge(customer_id, total, f"tok_{customer.id}")
        order_id = f"ORD-{next(self._orders):05d}"
        self._notify_in_background(customer_id, order_id)
        return OrderResult(order_id, payment.transaction_id, total, quantity)

    def _quote_in_parallel(
        self, customer_id: str, product_id: str, quantity: int
    ) -> tuple[Discount, ShippingEstimate]:
        """Fork-join: both quotes run on the pool and merge back under the order span."""
        ports = self._ports
        fork = ForkJoinGroup.create(self._context)
        discount = ports.executor.submit(
            fork.wrap(lambda: ports.discounts.calculate_discount(customer_id, product_id))
        )
        shipping = ports.executor.submit(
            fork.wrap(lambda: ports.shipping.estimate(product_id, quantity))
        )
        quotes = (discount.result(), shipping.result())
        fork.merge()
        return quotes

    def _notify_in_background(self, customer_id: str, order_id: str) -> None:
        """Fire-and-forget on the pool: the launcher marker is grafted now, exactly as any other
        fire-and-forget launch — the renderer's ``[launched, result not captured]`` line is real,
        this call really does not wait for or graft its result under that marker. It waits anyway
        and grafts the captured subtree plainly (concurrency tag stripped: this is the demo
        showing what happened, not the group merging a member), only so the trace stays
        deterministic to read; a real caller would return right after the launch. That subtree is
        where the second concurrency flavor lives: the worker runs ``asyncio.run`` over the async
        notifier, whose own ForkJoinGroup — created from inside the running coroutine — fans email
        confirmation and loyalty credit out over asyncio.gather and merges them back under it."""
        launcher = FireAndForgetGroup.create(self._context, "AsyncNotificationService")
        pending = self._ports.executor.submit(
            launcher.wrap(
                lambda: asyncio.run(
                    self._ports.notifications.notify_order_confirmed(customer_id, order_id)
                )
            )
        )
        pending.result()
        for root in launcher.child_roots():
            self._context.emit_trace_node(
                replace(root, concurrency=None), self._context.current_span_id()
            )


@dataclass(frozen=True, slots=True)
class Shop:
    """The traced object graph: every collaborator wrapped once, at composition time."""

    context: NarrativeContext
    orders: OrderService
    catalog: ProductCatalogService
    executor: ThreadPoolExecutor


def build_shop(context: NarrativeContext) -> Shop:
    """Wires the shop the way a container would: each service wrapped by ``trace_object``."""
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shop-worker")
    notifications = AsyncNotificationService(
        context,
        trace_object(EmailService(), context),
        trace_object(LoyaltyService(), context),
    )
    collaborators = Collaborators(
        customers=trace_object(CustomerService(), context),
        catalog=trace_object(ProductCatalogService(), context),
        inventory=trace_object(InventoryService(), context),
        discounts=trace_object(DiscountService(), context),
        shipping=trace_object(ShippingEstimateService(), context),
        payments=trace_object(PaymentService(), context),
        notifications=trace_object(notifications, context),
        executor=executor,
    )
    orders = trace_object(OrderService(context, collaborators), context)
    return Shop(context, orders, collaborators.catalog, executor)


# --------------------------------------------------------------------------- #
# Scenarios                                                                   #
# --------------------------------------------------------------------------- #
def _place_order(
    context: NarrativeContext, customer_id: str, product_id: str, quantity: int
) -> TraceTree:
    shop = build_shop(context)
    with shop.executor:
        try:
            shop.orders.place_order(customer_id, product_id, quantity)
        except (UnknownCustomerError, OutOfStockError, PaymentDeclinedError):
            pass  # expected: the trace records the failure, the reader reads it
    return context.capture_trace()


def capture_successful_order(context: NarrativeContext) -> TraceTree:
    return _place_order(context, "C-1234", "SKU-MECHANICAL-KB", 2)


def capture_payment_failure(context: NarrativeContext) -> TraceTree:
    return _place_order(context, "C-BROKE", "SKU-MOUSE-PAD", 3)


def capture_unknown_customer(context: NarrativeContext) -> TraceTree:
    return _place_order(context, "C-UNKNOWN", "SKU-MECHANICAL-KB", 1)


def capture_out_of_stock(context: NarrativeContext) -> TraceTree:
    return _place_order(context, "C-1234", "SKU-USB-HUB", 9999)


def capture_flaky_service(context: NarrativeContext) -> TraceTree:
    notifier = trace_object(FlakyNotificationService(NotificationService(), 2), context)
    notifier.notify_order_placed("C-1234", "ORD-00001")
    try:
        notifier.notify_order_placed("C-1234", "ORD-00002")
    except ExternalServiceError:
        pass  # expected
    return context.capture_trace()


def capture_worker_thread_lookups(context: NarrativeContext) -> TraceTree:
    """Looks a price up on the calling thread, then two more on a worker that captures itself."""
    shop = build_shop(context)
    shop.catalog.lookup_price("SKU-MECHANICAL-KB")

    def lookups_on_worker() -> TraceTree:
        shop.catalog.lookup_price("SKU-MOUSE-PAD")
        shop.catalog.lookup_price("SKU-USB-HUB")
        return context.capture_trace()

    with shop.executor:
        return shop.executor.submit(lookups_on_worker).result()


def scenarios() -> list[Scenario]:
    """The six scenarios in tour order."""
    return [
        Scenario(
            "Scenario 1: Successful Order + Async Notification",
            "Wiring: build_shop wraps every service with trace_object(service, context) — "
            "OrderService holds no tracing code at all. The // line in the tree is @narrated on "
            "OrderService.place_order; card_token prints as [REDACTED] because "
            "PaymentService.charge carries @not_traced('card_token'). Two concurrency flavors, "
            "one trace: discount and shipping run on a thread pool inside a ForkJoinGroup and "
            "merge back under the order (thread_name set on each child); the order-confirmed "
            "notification is a FireAndForgetGroup launcher on the same pool, and the worker it "
            "runs on drives AsyncNotificationService.notify_order_confirmed — a real async def "
            "whose own ForkJoinGroup, created from inside that coroutine, fans email "
            "confirmation and loyalty credit out over asyncio.gather and merges them back under "
            "it (thread_name is None on those children — asyncio, not a thread). Nesting an "
            "asyncio fork group's children under the coroutine that spawned them, instead of "
            "dropping them as roots, is what the 2026-09-08 core fix made correct.",
            capture_successful_order,
            sections=(TREE, PROSE, MARKDOWN, MERMAID),
        ),
        Scenario(
            "Scenario 2: Payment Failure — Inventory Leak Bug",
            "Wiring: unchanged from scenario 1 — nothing was added to catch or log this failure. "
            "The wrapper records the raised PaymentDeclinedError and unwinds the tree itself; "
            "the bracketed text after !! comes from @on_error on PaymentService.charge.",
            capture_payment_failure,
            notice=(
                "^ Notice: InventoryService.reserve was called but InventoryService.release is "
                "missing from the trace.",
            ),
        ),
        Scenario(
            "Scenario 3: Flaky External Service",
            "Wiring: no shop in this one — trace_object(FlakyNotificationService(...), context) "
            "wraps a plain decorator object at runtime. Same context as the shop above, so its "
            "calls would land in the same trace: a composition root is a convenience, not a "
            "requirement. @on_error on notify_order_placed supplies the bracketed message.",
            capture_flaky_service,
            sections=(TREE, PROSE),
        ),
        Scenario(
            "Scenario 4: Unknown Customer",
            "Wiring: unchanged — the same wrappers produced these lines. @on_error on "
            "CustomerService.find_customer supplies the bracketed message; run with --classic to "
            "see the same events as ordinary timestamped log lines.",
            capture_unknown_customer,
            sections=(TREE, PROSE),
        ),
        Scenario(
            "Scenario 5: Out of Stock",
            "Wiring: same wrappers; @on_error on InventoryService.reserve supplies the bracketed "
            "message. Reservation happens before the fork, so the failed order never quotes "
            "discount or shipping — the tree shows exactly how far the order got.",
            capture_out_of_stock,
            sections=(TREE, PROSE),
        ),
        Scenario(
            "Scenario 6: Explicit Async Trace Capture",
            "Wiring: the context keeps one trace stack per thread and per asyncio task "
            "(contextvars), so capture_trace() returns only the calling thread's story. The "
            "worker thread captured its own two lookups and handed the tree back; the "
            "main-thread lookup narrated above is not in it.",
            capture_worker_thread_lookups,
            sections=(TREE,),
            intro=(
                "Traces are thread-scoped: capture_trace() returns only the calling thread's",
                "story. The worker thread below captured its own calls and handed the tree back.",
            ),
        ),
    ]


def run_example(out: TextIO, *, classic: bool = False) -> None:
    """Walks all six scenarios, printing the sections to ``out``."""
    with narrated_run(out, classic=classic) as context:
        walk(scenarios(), out, context)


def main(argv: Sequence[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)
    run_example(sys.stdout, classic="--classic" in args)


if __name__ == "__main__":
    main()
