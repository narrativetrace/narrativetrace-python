# Send traces to the observability stack you already run

## The problem

> We already have tracing and dashboards. I am not adopting a second place to
> look — can this go into the stack we run?

Yes: one run, two consumers. The narrative lines keep going to your logger,
and the same events become OpenTelemetry spans on the way out. Below is one
checkout with both outputs side by side.

## Minimal setup

`narrativetrace-otel` (its [install line is on the installation page](../guides/installation.md))
plus the OpenTelemetry API, which the package leaves to you so your SDK version
wins. There are two ways in, and the difference is *when* a span exists:

| Mode | Class | Use it when |
|---|---|---|
| Live, as the methods run | `OtelTraceEventListener` | You want spans in your collector even if the process dies mid-request — this page |
| Batch, after the fact | `TraceSpanExporter` | You want the spans of a finished trace tree, exported once, at the lowest execution cost: `TraceSpanExporter(tracer).export(context.capture_trace().roots)` |

Either one is wired by you, in your own code: the context takes the event
store it should hand events to, and a store that also hands each event to a
consumer is how a second consumer joins the first
([OpenTelemetry guide](../guides/opentelemetry.md)). An in-memory exporter
stands in for your collector below, which is also the clearest picture of what
your real wiring does with a real one.

## The scenario

The store is the only new idea: it hands every event to the narration you
already have and to the OpenTelemetry listener, and keeps it for
`capture_trace()` like any store. The checkout itself is wrapped exactly as on
every other page:

<!-- snippet: examples/recipes/checkout/observability_fixture.py -->
```python
"""documentation/recipes/send-traces-to-the-observability-stack-you-already-run.md's scenario: ONE
run of the checkout writes the log lines it always wrote AND an OpenTelemetry span per traced call,
with the parentage and the attributes the page shows -- and without the redacted values (rule 8,
docs as tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process so the
log file the page embeds holds this scenario alone. No ``narrative_trace`` fixture, deliberately:
this page's subject is the context a deployment composes -- the narration it already has and an
OpenTelemetry listener, fed from one event store -- and an in-memory exporter stands in for the
collector. The exported spans are written out by ``write_exported_spans``, naming and sorting
everything it prints, so one run's dump is byte-identical to the next: a raw span dump carries
timestamps and OpenTelemetry's own generated ids and could never be embedded.
"""

import os
from pathlib import Path

from narrativetrace_otel import OtelTraceEventListener
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from examples.recipes.checkout.env import ARTIFACTS_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import (
    ContextVarNarrativeContext,
    LoggingTraceConsumer,
    TraceEvent,
    TraceId,
    trace_object,
)
from narrativetrace.pipeline.event_store import EventStore

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")
CARD_NUMBER = "4242424242424242"


# snippet:begin wiring
class NarratedAndExportedStore(EventStore):
    """Hands every event to the narration and to OpenTelemetry as it happens, and keeps it for
    ``capture_trace()`` -- the one place the two consumers meet."""

    def __init__(self, narration: LoggingTraceConsumer, export: OtelTraceEventListener) -> None:
        super().__init__()
        self._narration = narration
        self._export = export

    def add(self, event: TraceEvent) -> None:
        self._narration.accept(event)
        self._export(event)
        super().add(event)


# snippet:end wiring


def test_one_run_narrates_and_exports() -> None:
    spans = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    store = NarratedAndExportedStore(
        LoggingTraceConsumer(), OtelTraceEventListener(provider.get_tracer("narrativetrace"))
    )
    context = ContextVarNarrativeContext(store=store)
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    inventory = trace_object(stock, context)
    payments = trace_object(PaymentService(), context)
    orders = trace_object(repository, context)
    checkout = trace_object(OrderService(inventory, payments, orders), context)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, CARD_NUMBER)

    exported = spans.get_finished_spans()
    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert_one_span_per_traced_call(exported)
    assert_no_redacted_value_was_exported(exported)
    assert_parameters_are_typed(exported)
    write_exported_spans(exported)
    provider.shutdown()


def assert_one_span_per_traced_call(exported: tuple[ReadableSpan, ...]) -> None:
    """Four traced calls, four spans, ended innermost first -- and the tree is reconstructed."""
    assert [span.name for span in exported] == [
        "InventoryService.reserve",
        "PaymentService.charge",
        "OrderRepository.save",
        "OrderService.place_order",
    ]
    by_id = {span_id(span): span for span in exported}
    root = named(exported, "OrderService.place_order")
    charge = named(exported, "PaymentService.charge")
    assert charge.parent is not None
    assert by_id[charge.parent.span_id] is root
    assert root.parent is None


def assert_no_redacted_value_was_exported(exported: tuple[ReadableSpan, ...]) -> None:
    """What the deny-list caught never reaches the exporter either -- there is no attribute for
    it, not even one holding the marker."""
    attributes = {
        key: str(value) for span in exported for key, value in (span.attributes or {}).items()
    }
    assert "narrative.param.card_number" not in attributes
    assert "narrative.param.card" not in attributes
    assert not any(CARD_NUMBER in value for value in attributes.values())


def assert_parameters_are_typed(exported: tuple[ReadableSpan, ...]) -> None:
    """``quantity: 2`` is an integer attribute, not the string ``"2"``."""
    root = named(exported, "OrderService.place_order")
    assert root.attributes is not None
    assert root.attributes["narrative.param.quantity"] == 2
    assert isinstance(root.attributes["narrative.param.quantity"], int)


def span_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return int(span.context.span_id)


def named(exported: tuple[ReadableSpan, ...], name: str) -> ReadableSpan:
    return next(span for span in exported if span.name == name)


def write_exported_spans(exported: tuple[ReadableSpan, ...]) -> None:
    """The dump the page embeds: span name, parent, and every attribute, sorted by key."""
    names = {span_id(span): span.name for span in exported}
    lines: list[str] = []
    for span in exported:
        parent = names[span.parent.span_id] if span.parent else "(none — this is the root)"
        lines += [f"span: {span.name}", f"  parent: {parent}"]
        lines += [f"    {key}: {value}" for key, value in sorted((span.attributes or {}).items())]
    target = Path(os.environ[ARTIFACTS_ENV])
    target.mkdir(parents=True, exist_ok=True)
    (target / "exported-spans.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
```
<!-- /snippet -->

## The actual output

**The log lines**, unchanged by any of this — the same narration
[Add logging to this service](add-logging-to-this-service.md) produces:

<!-- snippet: examples/recipes/checkout/build/send-traces-to-the-observability-stack-you-already-run/checkout.log -->
```text
DEBUG [solid wand romps] [narrativetrace] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "PAY-C-1234-7998"
DEBUG [solid wand romps] [narrativetrace] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - ← returned: "ORD-C-1234-SKU-KB-2"
```
<!-- /snippet -->

**The spans that left the same run**, as the in-memory exporter received
them — name, parent and every attribute, sorted:

<!-- snippet: examples/recipes/checkout/build/send-traces-to-the-observability-stack-you-already-run/exported-spans.txt -->
```text
span: InventoryService.reserve
  parent: OrderService.place_order
    narrative.class: InventoryService
    narrative.method: reserve
    narrative.outcome: null
    narrative.param.quantity: 2
    narrative.param.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: PaymentService.charge
  parent: OrderService.place_order
    narrative.class: PaymentService
    narrative.method: charge
    narrative.outcome: "PAY-C-1234-7998"
    narrative.param.amount_cents: 7998
    narrative.param.customer_id: C-1234
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: OrderRepository.save
  parent: OrderService.place_order
    narrative.class: OrderRepository
    narrative.method: save
    narrative.outcome: null
    narrative.param.order.amount_cents: 7998
    narrative.param.order.customer_id: C-1234
    narrative.param.order.order_id: ORD-C-1234-SKU-KB-2
    narrative.param.order.quantity: 2
    narrative.param.order.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: OrderService.place_order
  parent: (none — this is the root)
    narrative.class: OrderService
    narrative.method: place_order
    narrative.outcome: "ORD-C-1234-SKU-KB-2"
    narrative.param.customer_id: C-1234
    narrative.param.quantity: 2
    narrative.param.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
```
<!-- /snippet -->

## How to read it

- **Four traced calls, four spans, one tree.** The spans arrive in the order
  they *ended* — innermost first, the root last, which is how any OTel
  pipeline sees a finished tree. Parentage is not inferred from that order or
  from an ambient context: the listener reads each event's explicit
  `parent_span_id`, which is why `InventoryService.reserve`,
  `PaymentService.charge` and `OrderRepository.save` all name
  `OrderService.place_order` as their parent even though they ended before it
  did.
- **What each span carries.** `narrative.class` and `narrative.method` are the
  call; `narrative.param.<name>` is one attribute per parameter, typed
  (`narrative.param.quantity: 2` is an integer, not the string `"2"` — the
  fixture asserts it); `narrative.outcome` is the returned value as the
  narration renders it, so a method that returned `None` carries
  `narrative.outcome: null`. `narrative.trace_id` and `narrative.trace_name`
  are NarrativeTrace's own identity for the trace, carried as attributes so a
  span in your backend can be matched to the log line and the trace file that
  describe the same call —
  [Follow one request across services](follow-one-request-across-services.md)
  is the same id doing the same job across a process boundary. The `nt.*`
  attributes mark the schema these attributes follow and the story the call
  belongs to.
- **A dataclass parameter arrives flattened.** `OrderRepository.save(order)` is
  one parameter, and it exported as `narrative.param.order.order_id`,
  `narrative.param.order.customer_id`, `narrative.param.order.sku`,
  `narrative.param.order.quantity`, `narrative.param.order.amount_cents` —
  field by field, because that is how the value was rendered: by reading its
  state, never by calling its `__str__`.
- **Redaction reaches this path too.** There is no
  `narrative.param.card_number` and no `narrative.param.card` attribute on any
  span above — not an attribute holding `[REDACTED]`, no attribute at all. A
  denied value is dropped at capture, before the event exists, so no consumer
  can receive it; the fixture asserts that as well as the span tree
  ([Keep secrets out of the logs](keep-secrets-out-of-the-logs.md)).
- **Which setting moved an event to which consumer.** Three decisions, in
  this order:
  1. The tracing level decides whether an event is created at all. At
     `SUMMARY` these same four spans are exported *without* the
     `narrative.param.*` attributes, because parameter values are not
     rendered at that level; at `OFF` there is no event, and therefore no
     span — both are asserted in this repository's recipe tests
     ([Trace in production without the cost](trace-in-production-without-the-cost.md)).
  2. The store decides who sees the event. Here one store hands each event to
     narration, then to export, then keeps it; retention — what
     `capture_trace()` and the trace files read — is untouched. Nothing was
     taken away from the logger to feed the exporter.
  3. Your logger's level decides what is *printed*. Raising the
     `narrativetrace` logger to `INFO` empties the log block above and
     changes nothing about the spans.
- **Why this is not a second place to look.** The spans are yours, in your
  collector, under your service name, beside the spans your framework already
  emits. What NarrativeTrace adds is a span per *traced method call* with the
  parameters and the outcome on it — one level below the HTTP span you
  already have.

## What is not captured

- **What your stack does with the spans is your stack's.** Sampling,
  retention, indexing and whether an attribute is searchable are the
  collector's and the backend's decisions. This page shows what leaves the
  process; no claim is made about any vendor's UI.
- **The ids are not shared.** OpenTelemetry generates its own trace and span
  ids for the spans it creates here, and NarrativeTrace's identity rides along
  as `narrative.trace_id` / `narrative.trace_name` attributes. A span's
  position in your backend's waterfall is OTel's; matching it to a log line is
  the attribute's job.
- **Live and batch are not the same spans.** This page's listener creates a
  span as a method runs, so an orphan (an enter with no exit — a process
  killed mid-call) ends up ended with an error status by the listener's own
  bounded map. The batch exporter only ever sees finished trees and adds
  `narrative.duration_ms`, which the live path does not.
- **The cost is a listener on the caller's thread.** The store runs both
  consumers inline, so span creation is on the path of the traced call. That
  is the trade for seeing the span while the method is still running; a
  buffered consumer moves it off the caller's thread at the price of shedding
  events under pressure, every loss counted ([README, Concurrency](../../README.md#concurrency)).
- **Only what is traced is exported.** No span exists for a call no
  integration intercepted — the export path inherits the boundary of the
  capture path exactly.

**The skill for this:** `narrativetrace-doctor` — one wiring check per
framework integration, and it reports whether any sink actually receives what
is traced.
