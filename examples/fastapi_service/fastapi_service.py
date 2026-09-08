# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""FastAPI/Starlette service traced end-to-end by the ASGI middleware.

Each request runs in a fresh narrative context. The handler resolves the request-scoped context
via ``get_narrative_context()`` and calls a ``trace_object``-wrapped service; at the request
boundary the middleware exports the captured tree with the real status code and duration.

    uvicorn examples.fastapi_service.fastapi_service:app
"""

from __future__ import annotations

from narrativetrace_asgi import (
    NarrativeTraceMiddleware,
    RequestContext,
    get_narrative_context,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from narrativetrace import ContextVarNarrativeContext, TraceTree, trace_object


class OrderService:
    """A traced domain service shared across the request."""

    def place_order(self, customer_id: str, product_id: str) -> str:
        return f"order for {customer_id}:{product_id}"


class CollectingExporter:
    """Records exported trees so the demo/tests can inspect the request boundary."""

    def __init__(self) -> None:
        self.calls: list[tuple[TraceTree, RequestContext]] = []

    def export(self, tree: TraceTree, request_context: RequestContext) -> None:
        self.calls.append((tree, request_context))


async def _place_order(request: Request) -> JSONResponse:
    context = get_narrative_context()
    assert context is not None  # bound by the middleware for the request's duration
    service = trace_object(OrderService(), context)
    result = service.place_order(request.path_params["customer_id"], "prod-42")
    return JSONResponse({"result": result})


def build_app(exporter: CollectingExporter | None = None) -> NarrativeTraceMiddleware:
    """Builds the traced ASGI app (Starlette wrapped by the narrative middleware)."""
    context = ContextVarNarrativeContext()
    inner = Starlette(routes=[Route("/orders/{customer_id}", _place_order)])
    return NarrativeTraceMiddleware(inner, context, exporter or CollectingExporter())


app = build_app()
