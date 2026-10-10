# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ASGI row's wiring, as the framework table shows it: ``NarrativeTraceMiddleware`` added to a
FastAPI app, with an exporter that prints each request's trace. Compiled and exercised by
``test_asgi_wiring.py``; the doctor's ``config.asgi-middleware`` fix and ``llms-full.md`` carry the
``wiring`` region verbatim (``narrativetrace_tooling/frameworks/wiring-snippets.md``)."""

from __future__ import annotations

# snippet:begin wiring
from fastapi import FastAPI
from narrativetrace_asgi import NarrativeTraceMiddleware, RequestContext

from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceTree, trace_object


class PrintingExporter:
    """Receives each request's trace at the request boundary; swap in your own sink."""

    def export(self, tree: TraceTree, request_context: RequestContext) -> None:
        print(IndentedTextRenderer().render(tree), flush=True)


context = ContextVarNarrativeContext()
app = FastAPI()
app.add_middleware(NarrativeTraceMiddleware, context=context, exporter=PrintingExporter())


@app.get("/orders/{customer_id}")
def place_order(customer_id: str) -> dict[str, str]:
    service = trace_object(OrderService(), context)
    return {"order": service.place_order(customer_id, "prod-42")}
    # snippet:end wiring


class OrderService:
    def place_order(self, customer_id: str, product_id: str) -> str:
        return f"ORD-{customer_id}-{product_id}"
