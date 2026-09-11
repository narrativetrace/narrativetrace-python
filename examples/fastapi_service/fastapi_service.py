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

import logging

from narrativetrace_asgi import (
    NarrativeTraceMiddleware,
    RequestContext,
    get_narrative_context,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from narrativetrace import (
    ContextVarNarrativeContext,
    LoggingTraceConsumer,
    NarrativeContextFilter,
    TraceEvent,
    TraceTree,
    trace_object,
)
from narrativetrace.pipeline.event_store import EventStore


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


class _LoggingEventStore(EventStore):
    """Forwards every request's enter/exit events to ``LoggingTraceConsumer`` as they happen —
    the ASGI composition root's equivalent of ``examples.tour._LiveStore``, without the
    fork/fire-and-forget graft suppression this single-service example never needs.
    """

    def __init__(self, consumer: LoggingTraceConsumer) -> None:
        super().__init__()
        self._consumer = consumer

    def add(self, event: TraceEvent) -> None:
        self._consumer(event)
        super().add(event)


def _configure_realistic_logger() -> None:
    """Send it to your logger — documentation/guides/logging.md. ``logging.basicConfig`` here
    stands in for a real ASGI app's logging setup; ``NarrativeContextFilter`` stamps every record
    (this bridge's own, and any the request handler logs itself) with the active span's keys plus
    the ``httpMethod``/``httpRoute``/``clientIp`` the middleware's ``request_log_scope`` opens for
    the request. A no-op once the root logger already has a handler (a test session's log capture,
    or a second import of this module), so it never fights another realistic configuration.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    handler.addFilter(NarrativeContextFilter())
    logging.basicConfig(level=logging.DEBUG, handlers=[handler])


async def _place_order(request: Request) -> JSONResponse:
    context = get_narrative_context()
    assert context is not None  # bound by the middleware for the request's duration
    service = trace_object(OrderService(), context)
    result = service.place_order(request.path_params["customer_id"], "prod-42")
    return JSONResponse({"result": result})


def build_app(exporter: CollectingExporter | None = None) -> NarrativeTraceMiddleware:
    """Builds the traced ASGI app (Starlette wrapped by the narrative middleware)."""
    _configure_realistic_logger()
    context = ContextVarNarrativeContext(store=_LoggingEventStore(LoggingTraceConsumer()))
    inner = Starlette(routes=[Route("/orders/{customer_id}", _place_order)])
    return NarrativeTraceMiddleware(inner, context, exporter or CollectingExporter())


app = build_app()
