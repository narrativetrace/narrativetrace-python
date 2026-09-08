# FastAPI / ASGI

`narrativetrace-asgi` wraps any ASGI app so each HTTP request is captured as one trace and
exported at the request boundary with the real status code and duration.

```python
from fastapi import FastAPI
from narrativetrace import ContextVarNarrativeContext, trace_object
from narrativetrace_asgi import NarrativeTraceMiddleware, get_narrative_context

context = ContextVarNarrativeContext()
app = FastAPI()

@app.get("/orders/{customer_id}")
def place_order(customer_id: str):
    ctx = get_narrative_context()          # the request-scoped context
    service = trace_object(OrderService(), ctx)
    return {"result": service.place_order(customer_id, "prod-42")}

app.add_middleware(NarrativeTraceMiddleware, context=context, exporter=my_exporter)
```

## Guarantees

- **Fail-safe** — throwing user/request extractors or exporters never fail the request and never
  mask the handler's own exception; the handler's error still propagates (and exports status 500).
- **Empty trees are not exported**; `excluded_paths` bypass tracing entirely.
- **Concurrent-request isolation** — each request runs in its own contextvars scope, so
  `asyncio.gather` of N requests never cross-contaminate.

## W3C traceparent

Inbound `traceparent` is adopted onto the request's trace id. For server-to-server calls, inject
it outbound on an `httpx` client:

```python
import httpx
from narrativetrace_asgi import attach_traceparent

client = httpx.AsyncClient(event_hooks={"request": [attach_traceparent]})
```

See the runnable [`examples/fastapi_service`](../../examples/fastapi_service).
