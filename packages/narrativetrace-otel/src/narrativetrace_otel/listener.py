# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Live event-stream bridge from NarrativeTrace events to OpenTelemetry spans.

``OtelTraceEventListener``. Plug this into the core pipeline as an event consumer to
create spans as methods execute rather than after the whole tree is built. A
:class:`~narrativetrace.pipeline.perishable.PerishableMap` of active spans is keyed by
NarrativeTrace :class:`~narrativetrace.ids.SpanId`: an enter starts a span, the matching exit
ends it. Orphaned spans (enter without exit) are evicted by the map's TTL/capacity limits and
ended with :data:`~opentelemetry.trace.StatusCode.ERROR` description ``"orphaned"``.

Parent-child links are reconstructed from explicit NarrativeTrace parent span ids, not from
OTel's ambient context alone, so interleaved enter/exit pairs from concurrent traces resolve
correctly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry.trace import Span, Status, StatusCode, Tracer, set_span_in_context

from narrativetrace.events import EnterEvent, ExitEvent, TraceEvent
from narrativetrace.pipeline.perishable import PerishableMap
from narrativetrace_otel import attributes

if TYPE_CHECKING:
    from narrativetrace.ids import SpanId
    from narrativetrace.signature import MethodSignature

_DEFAULT_MAX_ACTIVE_SPANS = 1024
_DEFAULT_TTL_SECONDS = 3600.0


@dataclass(frozen=True, slots=True)
class _SpanFrame:
    """Pairs an OTel span with the signature captured at enter time."""

    span: Span
    signature: MethodSignature


class OtelTraceEventListener:
    """Consumes :class:`~narrativetrace.events.TraceEvent` and produces OTel spans live."""

    def __init__(
        self,
        tracer: Tracer,
        max_active_spans: int = _DEFAULT_MAX_ACTIVE_SPANS,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._tracer = tracer
        self._active_spans: PerishableMap[SpanId, _SpanFrame] = PerishableMap(
            max_active_spans, ttl_seconds, lambda frame: _end_as_orphaned(frame.span)
        )

    def __call__(self, event: TraceEvent) -> None:
        """Dispatches an event; non enter/exit events are ignored."""
        if isinstance(event, EnterEvent):
            self._handle_enter(event)
        elif isinstance(event, ExitEvent):
            self._handle_exit(event)

    def _handle_enter(self, enter: EnterEvent) -> None:
        sig = enter.signature
        sc = enter.span_context
        name = f"{sig.class_name}.{sig.method_name}"
        parent_frame = (
            self._active_spans.get(sc.parent_span_id) if sc.parent_span_id is not None else None
        )
        context = set_span_in_context(parent_frame.span) if parent_frame is not None else None
        span = self._tracer.start_span(name, context=context, start_time=enter.timestamp_nanos)
        attributes.set_span_attributes(sig, span)
        attributes.set_trace_identity_attributes(sc, span)
        attributes.set_nt_schema_attributes(sc, span)
        if sc.parent_span_id is None:
            attributes.set_trace_level_attributes(sc, span)
        self._active_spans.put(sc.span_id, _SpanFrame(span, sig))

    def _handle_exit(self, exit_event: ExitEvent) -> None:
        frame = self._active_spans.remove(exit_event.span_context.span_id)
        if frame is None:
            self._handle_exit_without_enter(exit_event)
            return
        attributes.set_outcome_attributes(exit_event.outcome, frame.span)
        frame.span.end(end_time=exit_event.timestamp_nanos)
        self._emit_event_on_parent(exit_event, frame.signature)

    def _emit_event_on_parent(self, exit_event: ExitEvent, sig: MethodSignature) -> None:
        parent_span_id = exit_event.span_context.parent_span_id
        if parent_span_id is None:
            return
        parent_frame = self._active_spans.get(parent_span_id)
        if parent_frame is None:
            return
        attrs = attributes.build_event_attributes(sig, exit_event.outcome)
        name = f"{sig.class_name}.{sig.method_name}"
        parent_frame.span.add_event(name, attributes=attrs, timestamp=exit_event.timestamp_nanos)

    def _handle_exit_without_enter(self, exit_event: ExitEvent) -> None:
        sc = exit_event.span_context
        span = self._tracer.start_span(str(sc.span_id), start_time=exit_event.timestamp_nanos)
        attributes.set_trace_identity_attributes(sc, span)
        attributes.set_trace_level_attributes(sc, span)
        attributes.set_outcome_attributes(exit_event.outcome, span)
        span.set_status(Status(StatusCode.ERROR, "orphaned — enter event lost"))
        span.end(end_time=exit_event.timestamp_nanos)


def _end_as_orphaned(span: Span) -> None:
    span.set_status(Status(StatusCode.ERROR, "orphaned — exit event lost"))
    span.end()
