# Follow a flow across threads

## The problem

> The checkout hands the slow parts to a thread pool. The trace stops at the
> submit and I cannot see what the background work did.

A thread knows nothing about the trace another thread is in, so handing work
to a pool hands over the work and nothing else. The trace has to be handed
over too — explicitly, at submission time. Below is one run that does, and one
that does not.

## Minimal setup

Nothing beyond the [install](../guides/installation.md): `ForkJoinGroup` and
`FireAndForgetGroup` are in `narrativetrace`, beside the context itself. Which
one depends on what the caller does next:

| The launching call | The helper | The ending step |
|---|---|---|
| Waits for the background work (this page) | `ForkJoinGroup` | `merge()`, after the tasks finish — it grafts what they recorded under the launching span |
| Returns without waiting | `FireAndForgetGroup` | None. The children are a separate record, read through `child_roots()` |

For coroutines the same groups take `await group.run_async(lambda: …)` instead
of `wrap(...)`. The [README's Concurrency section](../../README.md#concurrency)
is the short version of both.

The log lines are written the moment each call happens (a context whose store
hands every event to a `LoggingTraceConsumer`, the live path in the
[Logging Guide](../guides/logging.md)), with the thread and the raw trace id in
the format — on this page the thread column is half the story:

<!-- snippet: examples/recipes/checkout/correlation_logging.py region=threads-format -->
```python
THREADS_FORMAT = "%(levelname)-5s [%(threadName)s] [%(name)s] [%(traceId)s] - %(message)s"
```
<!-- /snippet -->

Two records in this page's log are not about a call — the fork and the join —
so they carry no trace id, and a format that names `traceId` would raise on
them. One small filter, which a project that logs these lines writes once:

<!-- snippet: examples/recipes/checkout/correlation_logging.py region=trace-id-filter -->
```python
class TraceIdOrBlank(logging.Filter):
    """The fork and join lines belong to no span, so they carry no ``traceId``: print a blank
    rather than let the format raise."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("traceId", "")
        return True


```
<!-- /snippet -->

## The scenario

**The checkout, with the two slow steps off its own thread.** The handover is
`group.wrap(...)` around each task and `group.merge()` after both are done:

<!-- snippet: examples/recipes/checkout/parallel_checkout.py -->
```python
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
```
<!-- /snippet -->

**The run — and the same work without the handover.** The second test
submits a traced call to the same pool with no group and no wrap, which is what
the code looked like before the handover was added:

<!-- snippet: examples/recipes/checkout/across_threads_fixture.py -->
```python
"""documentation/recipes/follow-a-flow-across-threads.md's scenario: the two tasks the checkout
hands to an executor stay inside the caller's trace when they are wrapped, and a task submitted
without the handover starts a trace of its own (rule 8, docs as tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs the first test alone for the log
the page embeds (the second one's trace id is freshly generated on every run, which is the finding
it reports and the one thing no embedded block can hold) and the second test in a run of its own.
One worker thread, named: the page embeds a real run's log byte for byte, and two threads logging
at once interleave differently every time. The handover is identical either way.
"""

import logging
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from examples.recipes.checkout import correlation_logging
from examples.recipes.checkout.env import ARTIFACTS_ENV
from examples.recipes.checkout.fraud import RuleBasedFraudCheck
from examples.recipes.checkout.live_logging import LoggingEventStore
from examples.recipes.checkout.parallel_checkout import ParallelCheckout
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, TraceNode, trace_object
from narrativetrace.render import StructuralTraceRenderer

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")

correlation_logging.install(correlation_logging.THREADS_FORMAT)


@pytest.fixture
def context() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext(store=LoggingEventStore(logging.getLogger("narrativetrace")))


@pytest.fixture
def workers() -> Iterator[ThreadPoolExecutor]:
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="checkout-worker")
    yield pool
    pool.shutdown(wait=True)


def test_the_background_tasks_stay_in_the_customers_trace(
    context: ContextVarNarrativeContext, workers: ThreadPoolExecutor
) -> None:
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    checkout = parallel_checkout(context, stock, repository, workers)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")

    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert stock.available_units("SKU-KB") == 3
    assert len(repository.saved()) == 1
    assert_the_children_came_home(context)
    write_structural_trace(context)


def assert_the_children_came_home(context: ContextVarNarrativeContext) -> None:
    """The merged children are under the span that launched them, in the caller's own trace."""
    root = context.capture_trace().roots[0]
    assert names(root.children) == [
        "InventoryService.reserve",
        "FraudCheckService.approve",
        "PaymentService.charge",
        "OrderRepository.save",
    ]
    reserve = root.children[0]
    assert reserve.span_context is not None
    assert root.span_context is not None
    assert reserve.span_context.trace_id == root.span_context.trace_id
    assert reserve.span_context.parent_span_id == root.span_context.span_id
    assert reserve.concurrency is not None
    assert reserve.concurrency.thread_name == "checkout-worker_0"


def test_a_task_submitted_without_the_handover_starts_a_new_trace(
    context: ContextVarNarrativeContext, workers: ThreadPoolExecutor
) -> None:
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    inventory = trace_object(stock, context)

    def reserve_and_report_the_trace() -> TraceId:
        inventory.reserve("SKU-KB", 2)
        return context.trace_id()

    # No ForkJoinGroup, no snapshot: the task is handed over, the trace is not.
    on_the_worker = workers.submit(reserve_and_report_the_trace).result()

    assert stock.available_units("SKU-KB") == 3
    assert on_the_worker != context.trace_id()
    assert "InventoryService.reserve" not in names(context.capture_trace().roots)


def parallel_checkout(
    context: ContextVarNarrativeContext,
    stock: InventoryService,
    repository: OrderRepository,
    workers: ThreadPoolExecutor,
) -> ParallelCheckout:
    inventory = trace_object(stock, context)
    fraud = trace_object(RuleBasedFraudCheck(), context, class_name="FraudCheckService")
    payments = trace_object(PaymentService(), context)
    orders = trace_object(repository, context)
    checkout = ParallelCheckout(context, inventory, fraud, payments, orders, workers)
    return trace_object(checkout, context, class_name="OrderService")


def names(nodes: list[TraceNode]) -> list[str]:
    return [f"{node.signature.class_name}.{node.signature.method_name}" for node in nodes]


def write_structural_trace(context: ContextVarNarrativeContext) -> None:
    """The caller's value-free structure, into the directory the page embeds from."""
    target = Path(os.environ[ARTIFACTS_ENV])
    target.mkdir(parents=True, exist_ok=True)
    document = StructuralTraceRenderer().render_document(
        context.capture_trace(), "The background tasks stay in the customers trace"
    )
    (target / "checkout.nt").write_text(document, encoding="utf-8")
```
<!-- /snippet -->

## The actual output

**The log of the run that keeps the trace:**

<!-- snippet: examples/recipes/checkout/build/follow-a-flow-across-threads/checkout.log -->
```text
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [MainThread] [narrativetrace] [] - ⑂ fork group created [groupId: fork-1]
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → FraudCheckService.approve(customer_id: "C-1234", amount_cents: 7998)
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: True
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → FraudCheckService.approve(customer_id: "C-1234", amount_cents: 7998)
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: True
DEBUG [MainThread] [narrativetrace] [] - ⑃ fork joined [groupId: fork-1, members: 2]
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "PAY-C-1234-7998"
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "ORD-C-1234-SKU-KB-2"
```
<!-- /snippet -->

**The structural trace of that run:**

<!-- snippet: examples/recipes/checkout/build/follow-a-flow-across-threads/checkout.nt -->
```text
scenario: The background tasks stay in the customers trace

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  ~ fork [2]
    #1.1 - FraudCheckService.approve(customer_id, amount_cents) → value
    #1.2 - InventoryService.reserve(sku, quantity) → value
  #1.3 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.4 - OrderRepository.save(order) → value
```
<!-- /snippet -->

The same trace rendered as Markdown (what the pytest plugin writes for a test
that uses its `narrative_trace` fixture) carries three things more — the
worker thread's name against each child, the join's wall time, and a
"sequential async" hint where the tasks did not overlap — and is not embedded
here because the numbers in them differ on every run.

## How to read it

- **The handover is visible, twice.**
  `⑂ fork group created [groupId: fork-1]` is the group being created, before
  either task is submitted; `⑃ fork joined [groupId: fork-1, members: 2]` is
  `merge()` reporting what came back. Between them is background work that
  belongs to this checkout. Those two lines carry an empty trace id — the last
  bracket is `[]` — because they are not span events: they are the group's own
  lifecycle, published by the context rather than by a traced call.
- **The children's lines carry the customer's trace id, on the worker's
  thread.** `InventoryService.reserve` and `FraudCheckService.approve` are
  written from `[checkout-worker_0]` with
  `[c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7]` — the same id as every `[MainThread]`
  line above and below them. That is the snapshot `group.wrap` took at
  submission time, activated on the worker.
- **Each child appears twice in the log, and once in the trace.** The first
  pair is the work happening, on `checkout-worker_0`. The second pair — the
  same two calls, same values, on `MainThread`, just before the join line —
  is `merge()` re-publishing them under the span that launched them, which is
  what puts them in the caller's tree. Read the log as a log: two writes, one
  event each. Read the `.nt` as the record: `#1.1` and `#1.2` under `#1`,
  inside `~ fork [2]`, exactly once.
- **The parent span id on each child is the launching span.** `#1.1` and
  `#1.2` name `#1` as their parent — not because they ran under it on the same
  thread (they did not) but because the group grafted them there. A log line
  cannot show this as a stable value (a span id is generated per span and
  would differ on every run), so `assert_the_children_came_home` above asserts
  it: each child's `parent_span_id` is the root's `span_id`, each child's
  `trace_id` is the root's, and the recorded thread is `checkout-worker_0`.
  That assertion is this page's proof.
- **How the second run differs.** Submit the same traced call with no wrap and
  the worker thread has no snapshot to activate, so its first traced call does
  what any first traced call does: it starts a trace. The second test asserts
  the two consequences — the trace id observed *on the worker* is not the
  caller's, and the caller's own captured trace contains no
  `InventoryService.reserve` at all. The work still happens, the stock is
  still reserved, the lines are still logged. They are simply somebody else's
  story, under an id nobody is searching for. That run's log is not embedded
  for the same reason: the id on its lines is new every time, and that is the
  finding.
- **Why "awaited sequentially" is the right diagnosis here.** The pool in this
  scenario has one thread, so the two tasks really do run one after the other
  and the Markdown rendering says so. That is a property of this scenario,
  chosen so one run's log is byte-stable enough to embed — not of the
  handover, which is the same code for a pool of any size.

## What is not captured

- **Work started without the handover starts a new trace.** That is the whole
  second half of this page: no wrap, no snapshot, no shared trace id. Nothing
  warns you, because from the library's point of view a fresh thread with a
  traced call on it is an ordinary new trace.
- **A framework that propagates context itself is covered only where its
  integration says so.** The ASGI middleware binds the request's context for
  the request's own task; work you push onto a thread pool from a handler is
  still yours to wrap. Outside what the [Feature Guide](../feature-guide.md)
  lists, assume the handover is yours to write.
- **`capture_trace()` reports the trace of the context it is asked on.** A
  capture taken from inside a worker's own stack sees that worker's spans, not
  the caller's — which is why the group, not the query, is what brings the two
  together.
- **A group without `merge()` collects nothing into the caller's trace.** The
  children are recorded, and then nothing grafts them: the log still shows
  them (with the right trace id), the caller's tree does not.
- **Work that outlives the call is a different helper.** `FireAndForgetGroup`
  has no merge step by design — the launching method has already returned, so
  there is nobody left to merge into.
- **Interleaving.** With a real pool the children's lines arrive in whatever
  order the threads get scheduled, which is why a log is read by trace id and
  not by position. The trace artifacts are unaffected: parentage comes from
  the snapshot, not from the order lines were written.

**The skill for this:** `narrativetrace-verify` — "runs async" and "crosses
threads" are two of the cases it exists for, and it reads the structural trace
against the intent before anything is called done.
