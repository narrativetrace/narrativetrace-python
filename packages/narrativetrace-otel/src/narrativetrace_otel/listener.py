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

Mode: the listener detects from the first span it starts whether the SDK mirrors NarrativeTrace
span ids (:class:`~narrativetrace_otel.id_generator.NarrativeTraceIdGenerator`). Mirrored, a
reconstructed parent is exact, so finished frames need no memory and nothing is marked synthetic;
otherwise (no generator installed, auto-instrumentation without the entry point, the API's no-op
tracer) the memory and the synthetic marking apply.

Parent-child links are reconstructed from explicit NarrativeTrace parent span ids, not from
OTel's ambient context alone, so interleaved enter/exit pairs from concurrent traces resolve
correctly.

A root whose NarrativeTrace parent span id is not an active frame (an adopted W3C ``traceparent``
names the caller's span, which never runs in this process) starts under a remote, non-recording
parent built from the span's trace id, parent span id and trace flags, so the backend joins it to
the caller's trace instead of showing a second root.

A child can start after its local parent has ended (work resumed from a ``snapshot()`` by a
scheduler, a fork or fire-and-forget member). Ended frames are remembered in a second bounded
map (same capacity and TTL as the active one), so such a child parents on its real OTel parent.
A child later than that memory (past the TTL, or past ``max_active_spans`` newer finished frames)
gets a parent context reconstructed from the NarrativeTrace parent id: a *local* context (never
presented as a remote, backend-known one), marked on the child with
``narrative.parent.synthetic=true`` and ``narrative.parent_span_id``. The two unknown-parent cases
are told apart by the enter event: a span opened by local hand-off (snapshot, fork,
fire-and-forget) carries :class:`~narrativetrace.concurrency.ConcurrencyInfo`; a root under an
adopted ``traceparent`` does not, and keeps the header's remote parent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry.context import Context
from opentelemetry.trace import (
    NonRecordingSpan,
    Span,
    Status,
    StatusCode,
    TraceFlags,
    Tracer,
    set_span_in_context,
)
from opentelemetry.trace import (
    SpanContext as OtelSpanContext,
)

from narrativetrace.events import EnterEvent, ExitEvent, TraceEvent
from narrativetrace.pipeline.perishable import PerishableMap
from narrativetrace_otel import attributes, id_handoff
from narrativetrace_otel.id_handoff import IdSource
from narrativetrace_otel.monotonic_to_epoch import MonotonicToEpoch

if TYPE_CHECKING:
    from narrativetrace.ids import SpanId
    from narrativetrace.signature import MethodSignature
    from narrativetrace.span import SpanContext

_PARENT_SYNTHETIC = "narrative.parent.synthetic"
_PARENT_SPAN_ID = "narrative.parent_span_id"
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
        epoch: MonotonicToEpoch | None = None,
    ) -> None:
        self._tracer = tracer
        # Events carry the monotonic clock; OTel wants epoch nanos. Anchored once, at construction.
        self._epoch = epoch if epoch is not None else MonotonicToEpoch()
        # None until the first span starts; then whether the SDK mirrors NarrativeTrace span ids.
        self._mirrored: bool | None = None
        self._active_spans: PerishableMap[SpanId, _SpanFrame] = PerishableMap(
            max_active_spans, ttl_seconds, lambda frame: _end_as_orphaned(frame.span)
        )
        # Parents a span may still name although they are not active: ended local frames and
        # remote parents adopted from a traceparent. Bounded like the active map; ages out silently.
        self._known_parents: PerishableMap[SpanId, OtelSpanContext] = PerishableMap(
            max_active_spans, ttl_seconds, lambda _forgotten: None
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
        parent, synthetic = self._parent_context(enter)
        span = self._start_mirrored(
            name, sc, parent, self._epoch.epoch_nanos(enter.timestamp_nanos)
        )
        if synthetic and self._mirrored is not True and sc.parent_span_id is not None:
            span.set_attribute(_PARENT_SYNTHETIC, True)
            span.set_attribute(_PARENT_SPAN_ID, sc.parent_span_id.value)
        attributes.set_span_attributes(sig, span)
        attributes.set_trace_identity_attributes(sc, span)
        attributes.set_nt_schema_attributes(sc, span)
        if sc.parent_span_id is None:
            attributes.set_trace_level_attributes(sc, span)
        self._active_spans.put(sc.span_id, _SpanFrame(span, sig))

    def _start_mirrored(
        self, name: str, sc: SpanContext, parent: Context | None, start_nanos: int
    ) -> Span:
        """Starts the span with its NarrativeTrace ids on offer, and learns the mode from the
        first one: ids are mirrored when the SDK's span id equals the NarrativeTrace span id."""
        offer = id_handoff.offer(sc, IdSource.LIVE)
        try:
            span = self._tracer.start_span(name, context=parent, start_time=start_nanos)
        finally:
            id_handoff.withdraw(offer)
        if self._mirrored is None:
            self._mirrored = span.get_span_context().span_id == int(sc.span_id.value, 16)
        return span

    def _parent_context(self, enter: EnterEvent) -> tuple[Context | None, bool]:
        """Resolves the parent: an active frame; else a remembered one (an ended local frame, or an
        adopted remote parent); else the id is known to nobody here -- the remote context an
        adopted ``traceparent`` named, or, for a span opened by local hand-off, a local context
        reconstructed from the NarrativeTrace parent id. Returns ``(context, reconstructed)``."""
        sc = enter.span_context
        parent_id = sc.parent_span_id
        if parent_id is None:
            return None, False
        parent_frame = self._active_spans.get(parent_id)
        if parent_frame is not None:
            return set_span_in_context(parent_frame.span), False
        known = self._known_parents.get(parent_id)
        if known is not None:
            return set_span_in_context(NonRecordingSpan(known)), False
        if enter.concurrency is None:
            remote = _remote_parent(sc, parent_id)
            self._known_parents.put(parent_id, remote)
            return set_span_in_context(NonRecordingSpan(remote)), False
        return set_span_in_context(NonRecordingSpan(_reconstructed_parent(sc, parent_id))), True

    def _handle_exit(self, exit_event: ExitEvent) -> None:
        frame = self._active_spans.remove(exit_event.span_context.span_id)
        if frame is None:
            self._handle_exit_without_enter(exit_event)
            return
        attributes.set_outcome_attributes(exit_event.outcome, frame.span)
        frame.span.end(end_time=self._epoch.epoch_nanos(exit_event.timestamp_nanos))
        if self._mirrored is not True:
            self._known_parents.put(exit_event.span_context.span_id, frame.span.get_span_context())
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
        parent_frame.span.add_event(
            name, attributes=attrs, timestamp=self._epoch.epoch_nanos(exit_event.timestamp_nanos)
        )

    def _handle_exit_without_enter(self, exit_event: ExitEvent) -> None:
        sc = exit_event.span_context
        at = self._epoch.epoch_nanos(exit_event.timestamp_nanos)
        span = self._tracer.start_span(str(sc.span_id), start_time=at)
        attributes.set_trace_identity_attributes(sc, span)
        attributes.set_trace_level_attributes(sc, span)
        attributes.set_outcome_attributes(exit_event.outcome, span)
        span.set_status(Status(StatusCode.ERROR, "orphaned — enter event lost"))
        span.end(end_time=at)


def _remote_parent(sc: SpanContext, parent_span_id: SpanId) -> OtelSpanContext:
    return OtelSpanContext(
        trace_id=int(sc.trace_id.value, 16),
        span_id=int(parent_span_id.value, 16),
        is_remote=True,
        trace_flags=TraceFlags(sc.trace_flags),
    )


def _reconstructed_parent(sc: SpanContext, parent_span_id: SpanId) -> OtelSpanContext:
    """A LOCAL parent built from the NarrativeTrace id: exact only when the SDK mirrors ids."""
    return OtelSpanContext(
        trace_id=int(sc.trace_id.value, 16),
        span_id=int(parent_span_id.value, 16),
        is_remote=False,
        trace_flags=TraceFlags(sc.trace_flags),
    )


def _end_as_orphaned(span: Span) -> None:
    span.set_status(Status(StatusCode.ERROR, "orphaned — exit event lost"))
    span.end()
