# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
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
