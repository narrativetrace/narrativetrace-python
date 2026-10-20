# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""documentation/recipes/follow-one-request-across-services.md's scenario: the checkout charges a
card through a second service over HTTP, the W3C ``traceparent`` goes with the request, and the
payment service's own trace carries the caller's trace id (rule 8, docs as tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process so the
log file the page embeds holds this scenario alone. The checkout is a Starlette app behind
``NarrativeTraceMiddleware`` -- the request integration the caller needs for ``attach_traceparent``
to know which trace it is in -- driven by ``TestClient`` with the end user's own ``traceparent``.
"""

import logging
import os
from pathlib import Path

from narrativetrace_asgi import NarrativeTraceMiddleware, RequestContext, parse_traceparent
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from examples.recipes.checkout import correlation_logging
from examples.recipes.checkout.env import ARTIFACTS_ENV
from examples.recipes.checkout.http_payment_service import HttpPaymentService
from examples.recipes.checkout.live_logging import LoggingEventStore
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.payment_service_process import PaymentServiceProcess
from examples.recipes.checkout.services import InventoryService, OrderRepository
from narrativetrace import ContextVarNarrativeContext, MarkdownRenderer, TraceTree, trace_object
from narrativetrace.render import StructuralTraceRenderer

# The trace the end user's request arrives in, fixed so the page's embedded artifacts name the same
# trace every run. A real client sends whatever its own tracing generated.
DEMO_TRACEPARENT = "00-c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7-c4e1d0a7c4e1d0a7-01"
SCENARIO = "A customer checks out against the payment service"

correlation_logging.install(correlation_logging.SERVICES_FORMAT)


class CapturedRequest:
    """The exporter the middleware hands the finished tree to, kept for the test to read."""

    tree: TraceTree | None = None

    def export(self, tree: TraceTree, request_context: RequestContext) -> None:
        self.tree = tree


def checkout_app(
    context: ContextVarNarrativeContext,
    exporter: CapturedRequest,
    stock: InventoryService,
    repository: OrderRepository,
    payment_endpoint: str,
) -> Starlette:
    """The checkout as a service: one route, the HTTP payment client where the local one was."""

    async def place_order(request: Request) -> JSONResponse:
        inventory = trace_object(stock, context)
        client = HttpPaymentService(payment_endpoint)
        payments = trace_object(client, context, class_name="PaymentService")
        orders = trace_object(repository, context)
        checkout = trace_object(OrderService(inventory, payments, orders), context)
        try:
            order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")
        finally:
            client.close()
        return JSONResponse({"order_id": order_id})

    middleware = [Middleware(NarrativeTraceMiddleware, context=context, exporter=exporter)]
    return Starlette(
        routes=[Route("/checkout", place_order, methods=["POST"])], middleware=middleware
    )


def test_a_customer_checks_out_against_the_payment_service() -> None:
    caller = ContextVarNarrativeContext(
        store=LoggingEventStore(logging.getLogger("narrativetrace"))
    )
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    exporter = CapturedRequest()

    with PaymentServiceProcess() as payment_service:
        app = checkout_app(caller, exporter, stock, repository, payment_service.endpoint)
        response = TestClient(app).post("/checkout", headers={"traceparent": DEMO_TRACEPARENT})

    assert response.json() == {"order_id": "ORD-C-1234-SKU-KB-2"}
    assert len(repository.saved()) == 1
    write_artifacts(exporter.tree, payment_service.last_trace)
    assert_the_trace_crossed_the_wire(payment_service, exporter.tree)


def assert_the_trace_crossed_the_wire(
    payment_service: PaymentServiceProcess, caller: TraceTree | None
) -> None:
    """One trace id, two services, one parent link: the header named the caller's trace and its
    ``charge`` span, and the payment service's root adopted both instead of starting a trace of
    its own."""
    sent = parse_traceparent(payment_service.inbound_traceparent)
    assert sent is not None
    assert str(sent.trace_id) == DEMO_TRACEPARENT.split("-")[1]

    assert payment_service.last_trace is not None
    callee_root = payment_service.last_trace.roots[0]
    assert callee_root.signature.method_name == "charge"
    assert callee_root.span_context is not None
    assert callee_root.span_context.trace_id == sent.trace_id
    # The parent crosses the wire too: the header's parent-id field names the caller's client
    # span, and the payment service's root records it as its parent.
    assert caller is not None
    client_span = caller.roots[0].children[1]
    assert client_span.signature.method_name == "charge"
    assert client_span.span_context is not None
    assert sent.span_id == client_span.span_context.span_id
    assert callee_root.span_context.parent_span_id == client_span.span_context.span_id


def write_artifacts(caller: TraceTree | None, callee: TraceTree | None) -> None:
    """The caller's value-free structure and the payment service's own narrative, into the
    directory the page embeds from."""
    assert caller is not None
    assert callee is not None
    target = Path(os.environ[ARTIFACTS_ENV])
    target.mkdir(parents=True, exist_ok=True)
    (target / "checkout.nt").write_text(
        StructuralTraceRenderer().render_document(caller, SCENARIO), encoding="utf-8"
    )
    (target / "payment-service.md").write_text(MarkdownRenderer().render(callee), encoding="utf-8")
