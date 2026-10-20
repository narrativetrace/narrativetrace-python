# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
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
