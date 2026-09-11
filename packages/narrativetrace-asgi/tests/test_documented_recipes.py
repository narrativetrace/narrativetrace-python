# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Real, end-to-end proof of the exact incantation `documentation/guides/fastapi-asgi.md` teaches
— `app.add_middleware(NarrativeTraceMiddleware, context=..., exporter=...)` on a real `FastAPI`
app.

Every other test in this package (`test_middleware.py`'s `_build_app`) and every example under
`examples/` (`examples/fastapi_service/fastapi_service.py`) wraps `NarrativeTraceMiddleware`
around a `Starlette` app by calling its constructor directly — `NarrativeTraceMiddleware(app,
context, exporter)` — never through Starlette's `add_middleware(cls, **kwargs)` protocol the
guide documents, and never through a real `fastapi.FastAPI` app (the guide's own headline
framework). A future change that broke that protocol specifically — e.g. making `context`/
`exporter` positional-only, which `add_middleware` calls as keyword arguments — could pass the
whole suite while breaking the doc, the same class of gap the .NET port's first release shipped
with (a documented quickstart the test suite never actually ran).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from narrativetrace_asgi import NarrativeTraceMiddleware, RequestContext, get_narrative_context

from narrativetrace import ContextVarNarrativeContext, trace_object
from narrativetrace.tree import TraceTree


class OrderService:
    """The same domain service `examples/fastapi_service` uses — a traced collaborator wrapped
    once and shared across the request, exactly as the guide's snippet shows."""

    def place_order(self, customer_id: str, product_id: str) -> str:
        return f"order for {customer_id}:{product_id}"


class RecordingExporter:
    """Captures every (tree, request_context) pair the middleware exports."""

    def __init__(self) -> None:
        self.calls: list[tuple[TraceTree, RequestContext]] = []

    def export(self, tree: TraceTree, request_context: RequestContext) -> None:
        self.calls.append((tree, request_context))


def test_add_middleware_matches_the_documented_fastapi_recipe() -> None:
    context = ContextVarNarrativeContext()
    exporter = RecordingExporter()
    app = FastAPI()

    @app.get("/orders/{customer_id}")
    def place_order(customer_id: str) -> dict[str, str]:
        ctx = get_narrative_context()  # the request-scoped context, exactly as the guide shows
        assert ctx is not None  # bound by the middleware for the request's duration
        service = trace_object(OrderService(), ctx)
        return {"result": service.place_order(customer_id, "prod-42")}

    # The exact documentation/guides/fastapi-asgi.md line under test.
    app.add_middleware(NarrativeTraceMiddleware, context=context, exporter=exporter)

    client = TestClient(app)
    response = client.get("/orders/cust-1")

    assert response.status_code == 200
    assert response.json() == {"result": "order for cust-1:prod-42"}
    assert len(exporter.calls) == 1
    tree, request_context = exporter.calls[0]
    assert not tree.is_empty
    assert request_context.status_code == 200


def test_add_middleware_still_adopts_an_inbound_traceparent() -> None:
    """The guide's other headline claim — "Inbound traceparent is adopted onto the request's
    trace id" — proven through the same `add_middleware` registration, not the constructor."""
    context = ContextVarNarrativeContext()
    exporter = RecordingExporter()
    app = FastAPI()

    @app.get("/orders/{customer_id}")
    def place_order(customer_id: str) -> dict[str, bool]:
        ctx = get_narrative_context()
        assert ctx is not None
        trace_object(OrderService(), ctx).place_order(customer_id, "prod-42")
        return {"ok": True}

    app.add_middleware(NarrativeTraceMiddleware, context=context, exporter=exporter)

    inbound = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    client = TestClient(app)
    response = client.get("/orders/cust-1", headers={"traceparent": inbound})

    assert response.status_code == 200
    tree, _request_context = exporter.calls[0]
    root_span_context = tree.roots[0].span_context
    assert root_span_context is not None
    assert str(root_span_context.trace_id) == "4bf92f3577b34da6a3ce929d0e0e4736"
