# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Maps NarrativeTrace signatures, span contexts, and outcomes to OTel span attributes.

``SpanContextAttributeMapper`` — the single source of truth shared by the live
:class:`~narrativetrace_otel.listener.OtelTraceEventListener` and the batch
:class:`~narrativetrace_otel.exporter.TraceSpanExporter`.

Trace-level attributes (``narrative.service.*``, ``narrative.http.*``, user identity) apply only
to root spans; span-level attributes (class, method, params) apply to every span. Structured
:class:`~narrativetrace.values.RenderedValue` values flatten to natively-typed OTel attributes
(int, float, bool, homogeneous arrays); object fields dot-flatten to depth 3. When a structured
value is absent, a string-inference fallback parses the flat rendered string.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from opentelemetry.trace import Span, Status, StatusCode

from narrativetrace.canonical import SCHEMA_VERSION
from narrativetrace.context_export import export as context_export
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.values import (
    BoolVal,
    FloatVal,
    InstantVal,
    IntVal,
    ListVal,
    ObjectVal,
    RenderedValue,
    StringVal,
)

if TYPE_CHECKING:
    from narrativetrace.concurrency import ConcurrencyInfo
    from narrativetrace.nodes import TraceNode
    from narrativetrace.signature import MethodSignature, ParameterCapture
    from narrativetrace.span import SpanContext

MAX_FLATTEN_DEPTH = 3

# OTel attribute values are str | bool | int | float | sequences thereof.
AttributeValue = str | bool | int | float | list[str] | list[bool] | list[int] | list[float]
Sink = Callable[[str, AttributeValue], None]

# Root-only trace-level fields: attribute key -> SpanContext extractor.
_TRACE_LEVEL_FIELDS: list[tuple[str, Callable[[SpanContext], object]]] = [
    ("narrative.service.name", lambda sc: sc.service_name),
    ("narrative.service.version", lambda sc: sc.service_version),
    ("narrative.service.environment", lambda sc: sc.environment),
    ("narrative.http.method", lambda sc: sc.http_method),
    ("narrative.http.route", lambda sc: sc.http_route),
    ("narrative.client_ip", lambda sc: sc.client_ip),
    ("narrative.enduser.id", lambda sc: sc.enduser_id),
    ("narrative.session.id", lambda sc: sc.session_id),
    ("narrative.tenant.id", lambda sc: sc.tenant_id),
]


def set_span_attributes(sig: MethodSignature, span: Span) -> None:
    """Sets span-level attributes (class, method, params) from ``sig``."""
    span.set_attribute("narrative.class", sig.class_name)
    span.set_attribute("narrative.method", sig.method_name)
    for param in sig.parameters:
        _set_param(span.set_attribute, f"narrative.param.{param.name}", param)


def set_concurrency_attributes(info: ConcurrencyInfo | None, span: Span) -> None:
    """Sets concurrency attributes from ``info`` when present."""
    if info is None:
        return
    span.set_attribute("narrative.concurrency.groupId", info.group_id)
    span.set_attribute("narrative.concurrency.kind", info.kind.name)
    span.set_attribute("narrative.concurrency.threadId", info.thread_id)
    if info.thread_name is not None:
        span.set_attribute("narrative.concurrency.threadName", info.thread_name)
    span.set_attribute("narrative.concurrency.virtual", info.virtual)
    if info.task_label is not None:
        span.set_attribute("narrative.concurrency.taskLabel", info.task_label)


def set_outcome_attributes(outcome: TraceOutcome | None, span: Span) -> None:
    """Sets outcome attributes/status from ``outcome``."""
    if isinstance(outcome, Returned):
        if outcome.rendered_value is not None:
            span.set_attribute("narrative.outcome", outcome.rendered_value)
    elif isinstance(outcome, Threw):
        span.set_status(Status(StatusCode.ERROR, str(outcome.exception)))
        span.record_exception(outcome.exception)
    elif isinstance(outcome, Incomplete):
        span.set_attribute("narrative.outcome", "in-flight")


def set_trace_identity_attributes(sc: SpanContext | None, span: Span) -> None:
    """Sets ``narrative.trace_id`` / ``narrative.trace_name`` on every span for correlation."""
    if sc is None:
        return
    span.set_attribute("narrative.trace_id", str(sc.trace_id))
    span.set_attribute("narrative.trace_name", sc.trace_id.human_name())


def set_nt_schema_attributes(sc: SpanContext | None, span: Span) -> None:
    """Sets canonical ``nt.*`` schema attributes on the span."""
    if sc is None:
        return
    span.set_attribute("nt.entryType", "entry")
    span.set_attribute("nt.schemaVersion", SCHEMA_VERSION)
    if sc.story_id is not None:
        span.set_attribute("nt.storyId", sc.story_id)
    if sc.chapter_id is not None:
        span.set_attribute("nt.chapterId", sc.chapter_id)


def set_trace_level_attributes(sc: SpanContext | None, span: Span) -> None:
    """Sets root-only trace-level attributes (service/http/user identity) from ``sc``.

    Adversarial-audit mirror (2026-09-02): a value set programmatically through
    ``set_request_context``/``set_user_context`` (a custom integration, a test, a framework this
    runtime ships no filter for) never passes through the HTTP middleware's own normalisation, so
    this is the last point before it becomes a telemetry attribute -- control-stripped and
    length-capped here regardless of how it arrived.
    """
    if sc is None:
        return
    for key, extractor in _TRACE_LEVEL_FIELDS:
        value = extractor(sc)
        if value is not None:
            span.set_attribute(key, context_export(str(value)))


def build_event_attributes(
    sig: MethodSignature, outcome: TraceOutcome | None
) -> dict[str, AttributeValue]:
    """Builds parent-span event attributes from a child's signature and outcome."""
    attrs: dict[str, AttributeValue] = {}
    for param in sig.parameters:
        if param.redacted or param.rendered_value == "":
            continue
        _set_param(_dict_sink(attrs), f"narrative.param.{param.name}", param, allow_lists=False)
    _add_outcome_to_event(attrs, outcome)
    return attrs


def emit_child_event(parent_span: Span, child: TraceNode) -> None:
    """Emits a child method completion as a timestamped event on the parent span."""
    attrs = build_event_attributes(child.signature, child.outcome)
    name = f"{child.signature.class_name}.{child.signature.method_name}"
    timestamp = child.start_time_nanos + child.duration_nanos
    parent_span.add_event(name, attributes=attrs, timestamp=timestamp)


def _dict_sink(attrs: dict[str, AttributeValue]) -> Sink:
    def sink(key: str, value: AttributeValue) -> None:
        attrs[key] = value

    return sink


def _set_param(
    sink: Sink, prefix: str, param: ParameterCapture, *, allow_lists: bool = True
) -> None:
    if param.redacted or param.rendered_value == "":
        return
    structured = param.structured_value
    if structured is None:
        sink(prefix, _typed_from_string(param.rendered_value))
    else:
        _flatten(structured, prefix, 0, sink, allow_lists=allow_lists)


def _flatten(
    value: RenderedValue, prefix: str, depth: int, sink: Sink, *, allow_lists: bool
) -> None:
    scalar = _scalar_native(value)
    if scalar is not None:
        sink(prefix, scalar)
        return
    if isinstance(value, ObjectVal) and depth < MAX_FLATTEN_DEPTH:
        for key, field_value in value.fields.items():
            _flatten(field_value, f"{prefix}.{key}", depth + 1, sink, allow_lists=allow_lists)
    elif allow_lists and isinstance(value, ListVal):
        array = _list_native(value)
        if array is not None:
            sink(prefix, array)
    # NullVal, depth-exceeded ObjectVal, and (in events) ListVal are skipped.


def _scalar_native(value: RenderedValue) -> AttributeValue | None:
    if isinstance(value, StringVal):
        return value.value
    if isinstance(value, BoolVal):
        return value.value
    if isinstance(value, IntVal):
        return value.value
    if isinstance(value, FloatVal):
        return value.value
    if isinstance(value, InstantVal):
        return value.epoch_millis
    return None


# Java emits homogeneous arrays only for these scalar types; all carry a ``.value`` field.
_ARRAY_ELEMENT_TYPES = (StringVal, BoolVal, IntVal, FloatVal)


def _list_native(value: ListVal) -> AttributeValue | None:
    if not value.elements:
        return None
    first = type(value.elements[0])
    if first not in _ARRAY_ELEMENT_TYPES:
        return None
    if any(type(element) is not first for element in value.elements):
        return None
    return [element.value for element in value.elements]  # type: ignore[attr-defined]


def _typed_from_string(rendered: str) -> AttributeValue:
    if rendered in ("true", "false"):
        return rendered == "true"
    parsed_int = _try_int(rendered)
    if parsed_int is not None:
        return parsed_int
    parsed_float = _try_float(rendered)
    if parsed_float is not None:
        return parsed_float
    if len(rendered) >= 2 and rendered.startswith('"') and rendered.endswith('"'):
        return rendered[1:-1]
    return rendered


def _try_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


def _try_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _add_outcome_to_event(attrs: dict[str, AttributeValue], outcome: TraceOutcome | None) -> None:
    if isinstance(outcome, Returned) and outcome.rendered_value is not None:
        attrs["narrative.outcome"] = outcome.rendered_value
    elif isinstance(outcome, Threw):
        attrs["narrative.outcome"] = f"error: {outcome.exception}"
