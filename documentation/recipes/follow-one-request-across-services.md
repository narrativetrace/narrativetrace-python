# Follow one request across services (distributed tracing)

## The problem

> The checkout calls the payment service over HTTP. When an order goes wrong,
> I want one request across both — not two logs I have to line up by hand.

Two services, two log files, two sets of ids. What makes them one story is a
single value travelling with the request: the W3C
[`traceparent`](https://www.w3.org/TR/trace-context/#traceparent-header)
header. The caller sends the trace it is in; the callee adopts that trace id
instead of starting a trace of its own. Below is one run of exactly that, with
both services' lines in one file.

## Minimal setup

Beyond the [install](../guides/installation.md) — `narrativetrace` for the
wrapper and the `logging` bridge, `narrativetrace-asgi` for the two halves of
the header, and `httpx` for the call — the caller needs
`NarrativeTraceMiddleware` (it is what tells the outbound hook which trace the
request is in) and one request hook on its client. The callee needs the
inbound half, and which code that is depends on how it is built:

| The callee is | The inbound half is |
|---|---|
| An ASGI application (FastAPI, Starlette) | `NarrativeTraceMiddleware`, which adopts the header for you ([FastAPI / ASGI guide](../guides/fastapi-asgi.md)) |
| Anything else — a plain `http.server`, a handler framework | A few lines in whatever runs first per request: reset, `adopt_trace_id(parsed.trace_id, parsed.span_id)` on the parsed header, serve |

This page's payment service is the second row: the checkout project runs
without a framework, so the handler reads the header itself. That is also the
honest example of what the middleware does, since it is the same sequence.

The log lines come from the `logging` bridge, as in
[Add logging to this service](add-logging-to-this-service.md), and the lines
are written the moment each call happens (a context whose store hands every
event to a `LoggingTraceConsumer`, the live path in the
[Logging Guide](../guides/logging.md)), because on this page *which service
wrote a line, and while the other was working* is the point. This page's
format puts the raw trace id in every line, because the trace id is the thing
being followed:

<!-- snippet: examples/recipes/checkout/correlation_logging.py region=services-format -->
```python
SERVICES_FORMAT = "%(levelname)-5s [%(name)s] [%(traceId)s] - %(message)s"
```
<!-- /snippet -->

## The scenario

**The caller's side: one hook.** The checkout's `PaymentService` is now an
HTTP client. It is an ordinary `httpx` client with `attach_traceparent` as a
request hook; the hook reads the trace the current request is in and sets one
header — everything else is an ordinary request:

<!-- snippet: examples/recipes/checkout/http_payment_service.py -->
```python
"""The checkout's payment collaborator when the payment service is a different process."""

from __future__ import annotations

import httpx
from narrativetrace_asgi import attach_traceparent

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.services import PaymentService

_DECLINED_STATUS = 402


class HttpPaymentService(PaymentService):
    """Charges a card by POSTing to the payment service's ``endpoint``.

    The outbound half of cross-service correlation, in the shape any ``httpx`` client copies:
    ``attach_traceparent`` is a request hook that stamps the current request's trace id and calling
    span onto the call as a W3C ``traceparent`` header. The body is a comma-separated line rather
    than JSON on purpose -- this class exists to show the header, and a parser would be the only
    thing a reader had to skip.
    """

    def __init__(self, endpoint: str) -> None:
        super().__init__()
        self._endpoint = endpoint
        self._client = httpx.Client(event_hooks={"request": [attach_traceparent]})

    def charge(self, customer_id: str, amount_cents: int, card: str) -> str:
        response = self._client.post(
            self._endpoint, content=f"{customer_id},{amount_cents},{card}".encode()
        )
        if response.status_code == _DECLINED_STATUS:
            raise PaymentDeclinedError(response.text)
        return response.text

    def close(self) -> None:
        self._client.close()
```
<!-- /snippet -->

**The callee's side: its own context.** The payment service is a second
service, which means a second narrative context — created with its own logger
name, so one log file can tell the two apart
(`examples/recipes/checkout/payment_service_process.py`):

<!-- snippet: examples/recipes/checkout/payment_service_process.py region=own-context -->
```python
        self.context = ContextVarNarrativeContext(
            store=LoggingEventStore(logging.getLogger(LOGGER_NAME))
        )
        self._payments = trace_object(PaymentService(), self.context)
```
<!-- /snippet -->

**The callee's side: adopt, serve, capture, reset.** This is the whole
inbound half, in the same file — and the same sequence
`NarrativeTraceMiddleware` performs for an ASGI application:

<!-- snippet: examples/recipes/checkout/payment_service_process.py region=inbound -->
```python
    def handle(self, exchange: BaseHTTPRequestHandler) -> None:
        header = exchange.headers.get("traceparent")
        self.inbound_traceparent = header
        self.context.reset()
        parsed = parse_traceparent(header)
        if parsed is not None:
            self.context.adopt_trace_id(parsed.trace_id, parsed.span_id)
        try:
            length = int(exchange.headers["Content-Length"])
            customer_id, amount_cents, card = exchange.rfile.read(length).decode().split(",", 2)
            reply(exchange, 200, self._payments.charge(customer_id, int(amount_cents), card))
        except PaymentDeclinedError as declined:
            reply(exchange, 402, str(declined))
        finally:
            self.last_trace = self.context.capture_trace()
            self.context.reset()
```
<!-- /snippet -->

**The run.** The checkout is a Starlette service behind
`NarrativeTraceMiddleware`, with the HTTP client where the local payment
service used to be, driven by `TestClient` with the end user's own
`traceparent`. The payment service is a loopback `HTTPServer` in the same
process: the request really crosses a socket and the header really arrives as a
header, which is what this page is about — a second process would add a second
interpreter and prove nothing further:

<!-- snippet: examples/recipes/checkout/across_services_fixture.py -->
```python
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
```
<!-- /snippet -->

## The actual output

**Both services' lines, one file** — the caller's under `narrativetrace`, the
payment service's under `narrativetrace.payments`:

<!-- snippet: examples/recipes/checkout/build/follow-one-request-across-services/checkout.log -->
```text
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [narrativetrace.payments] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [narrativetrace.payments] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "PAY-C-1234-7998"
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "PAY-C-1234-7998"
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "ORD-C-1234-SKU-KB-2"
```
<!-- /snippet -->

**The caller's own trace,** the value-free structural artifact of that run — the
span ids below are the ones this page reads by:

<!-- snippet: examples/recipes/checkout/build/follow-one-request-across-services/checkout.nt -->
```text
scenario: A customer checks out against the payment service

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.3 - OrderRepository.save(order) → value
```
<!-- /snippet -->

**The payment service's own narrative,** captured by its own context at the
end of the request and rendered beside the caller's:

<!-- snippet: examples/recipes/checkout/build/follow-one-request-across-services/payment-service.md mask=duration -->
```text
- **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #1
```
<!-- /snippet -->

## How to read it

- **One trace id, in both services' lines.**
  `c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7` is the second bracket of every line
  above, the caller's and the callee's alike. The caller's is the trace this
  run is in (the end user's header named it); the callee's is that same id
  because it *adopted* it. Nothing correlates them after the fact — they were
  never apart.
- **The two services are told apart by the logger, not by the id.**
  `[narrativetrace]` is the checkout, `[narrativetrace.payments]` is the
  payment service, because its context was built with a logger of that name.
  The payment service's two lines sit *between* the checkout's
  `→ PaymentService.charge` and its `← returned`, which is the order things
  happened in: the checkout was waiting while the other service worked.
- **The caller's `#1.2` and the callee's `#1` are the same work, seen from
  both ends.** In the caller's narrative, `#1.2 PaymentService.charge` is the
  *client* span: it starts when the checkout calls the client and ends when
  the response comes back, so it includes the whole round trip. In the payment
  service's narrative, `#1 PaymentService.charge` is the *server* span: the
  work it actually did. Span ids are per-trace-tree and each service numbers
  its own from `#1` — the join is the trace id, not the number.
- **What is asserted, because a log line cannot show it.** The fixture above
  reads the header the payment service actually received and checks three
  things: it carries the caller's trace id, the payment service's root span
  carries that same id, and the parent link below holds. That assertion is this
  page's proof.
- **The parent span id travels too.** The `traceparent` header's parent-id
  field carries the caller's `charge` span, and the payment service's root
  records it as its parent span id, so a backend that draws one waterfall from
  parent span ids draws one across the two services. The fixture asserts it:
  the header's parent equals the caller's client span id, and the callee's root
  parent equals the header's. The parent is an id only — it names a span in the
  caller's trace and never appears as a span in the payment service's own tree.
- **How to join them in a log search.** The trace id is on every record
  NarrativeTrace writes, in either service, as the `traceId` attribute. Put
  `%(traceId)s` in your format (as above) or a JSON formatter in front of it,
  and one request across both services is
  `grep c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7` — or, in whatever aggregator you
  run, `traceId:"c4e1…"`. The trace *name* that
  [Add logging to this service](add-logging-to-this-service.md) greps by is
  derived from the same id, so it works as a search key too, and reads better
  for a human.
- **The two narratives stay two.** The payment service's spans are in the
  payment service's trace, not in the caller's: `capture_trace()` on either
  side returns that side's work. One trace id, two trees — which is exactly
  what you have in production, where the other service is a different process
  on a different host.
- **Why the caller's `.nt` is embedded and not its Markdown.** The Markdown
  renderer marks any call slower than 200 ms, and a real HTTP round trip can
  cross that line on a loaded machine, so the Markdown of the caller's trace is
  not byte-stable. The value-free structural trace is, and it is the artifact
  that carries the span ids this page reads by.

## What is not captured

- **A hop through a service that does not forward the header breaks the
  chain.** Correlation is cooperative: the chain holds for as long as every
  service in it *passes `traceparent` on*. A proxy, a queue consumer or a
  third-party service that drops the header leaves the next NarrativeTrace
  service with nothing to adopt, and it starts a fresh trace — correctly, since
  it has no honest parent to name. A service with no NarrativeTrace at all is
  fine *if* it forwards the header it received.
- **No header is sent outside a traced request.** `attach_traceparent` reads
  the context `NarrativeTraceMiddleware` binds for the request; a call made
  from a script, a worker or a startup hook has none, and the client sends
  nothing rather than a header pointing at a trace that does not exist. An
  untraced call out of the checkout therefore cannot be joined, and that is by
  design. A request that already carries a `traceparent` of its own is left
  alone.
- **`traceparent` only.** The client above sends no `tracestate` and no
  baggage: nothing in this path reads or writes vendor state, and no
  application value crosses the wire because of tracing.
- **Nothing comes back.** The response carries no trace header, so the
  caller's narrative says what it sent and what it got, never what the callee
  did inside. The callee's own narrative is the record of that, and the trace
  id is what finds it.
- **Two services, one interpreter, one socket.** What this run does not
  exercise is a second process, a second environment and a network that can
  fail. The header mechanism is unchanged by any of those; the failure modes of
  the call itself are your HTTP client's.

**The skill for this:** `narrativetrace-verify` — a change that crosses
services is exactly the case it exists for: write the intent down, run the
smallest real path, and read the trace against it before calling it done.
