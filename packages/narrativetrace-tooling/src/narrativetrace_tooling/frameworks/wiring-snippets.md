# Wiring snippets — the framework table's lines

One section per framework-table row whose wiring is source-level, keyed by the row id. Every block
is a fixture's region the test suite runs, written here by `poe snippet-sync` and held to it by
`poe snippet-check`; the doctor's `config.<framework>-*` fix prints the block verbatim. Never edit a
block by hand — edit the fixture.

## pytest

<!-- snippet: packages/narrativetrace-pytest/tests/fixture_wiring.py region=wiring -->
```python
from narrativetrace import ContextVarNarrativeContext, trace_object


def test_place_order(narrative_trace: ContextVarNarrativeContext) -> None:
    service = trace_object(OrderService(), narrative_trace)

    assert service.place_order("cust-1", "prod-42") == "ORD-cust-1-prod-42"
```
<!-- /snippet -->

## asgi

<!-- snippet: packages/narrativetrace-asgi/tests/asgi_wiring.py region=wiring -->
```python
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
```
<!-- /snippet -->

## opentelemetry

<!-- snippet: packages/narrativetrace-otel/tests/otel_wiring.py region=wiring -->
```python
from narrativetrace_otel import OtelTraceEventListener
from opentelemetry import trace

from narrativetrace import ContextVarNarrativeContext, TraceEvent
from narrativetrace.pipeline.event_store import EventStore


class OtelEventStore(EventStore):
    """Hands every trace event to OpenTelemetry as it happens, and keeps it for capture_trace()."""

    def __init__(self, listener: OtelTraceEventListener) -> None:
        super().__init__()
        self._listener = listener

    def add(self, event: TraceEvent) -> None:
        self._listener(event)
        super().add(event)


context = ContextVarNarrativeContext(
    store=OtelEventStore(OtelTraceEventListener(trace.get_tracer("orders")))
)
```
<!-- /snippet -->

## structlog

<!-- snippet: packages/narrativetrace-structlog/tests/structlog_wiring.py region=wiring -->
```python
import structlog
from narrativetrace_structlog import narrative_context_processor

structlog.configure(
    processors=[narrative_context_processor, structlog.processors.JSONRenderer()],
)
```
<!-- /snippet -->

## default-logger

<!-- snippet: packages/narrativetrace/tests/logging_wiring.py region=wiring -->
```python
import logging
import sys

from narrativetrace import (
    ContextVarNarrativeContext,
    NarrativeContextFilter,
    export_to_logger,
    trace_object,
)

handler = logging.StreamHandler(sys.stdout)
handler.addFilter(NarrativeContextFilter())
logging.basicConfig(level=logging.DEBUG, handlers=[handler])


def place_order_and_log(customer_id: str) -> None:
    context = ContextVarNarrativeContext()
    trace_object(OrderService(), context).place_order(customer_id)
    export_to_logger(context.capture_trace())
```
<!-- /snippet -->
