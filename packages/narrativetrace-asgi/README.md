# narrativetrace-asgi

Pure-ASGI middleware that captures one [narrativetrace](../narrativetrace) trace tree per HTTP
request. Compatible with Starlette and FastAPI.

* **Fail-safe** — throwing request/user extractors or exporters never fail the request and never
  mask the handler's own exception.
* **Request-boundary export** — the captured tree is exported in a `finally` block with the real
  status code and duration; an empty tree is never exported.
* **W3C `traceparent`** — inbound trace-id adoption plus an outbound injection helper for `httpx`.
* **Request-scoped accessor** — `get_narrative_context()` returns the context bound to the
  in-flight request (contextvars-based, so concurrent requests are isolated).
