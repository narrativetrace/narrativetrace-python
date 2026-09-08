# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for the canonical entry invariants."""

from __future__ import annotations

import json
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from narrativetrace.canonical import (
    SCHEMA_VERSION,
    MonotonicAnchor,
    entry_document,
    entry_from_event,
    entry_to_json,
)
from narrativetrace.events import (
    EnterEvent,
    ExitEvent,
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
    TraceEvent,
)
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext

ANCHOR = MonotonicAnchor(epoch_millis=1_775_000_000_000, monotonic_nanos=5_000_000_000)
CANONICAL_ORDER = (
    "timestamp",
    "level",
    "message",
    "service",
    "environment",
    "host.name",
    "process.pid",
    "process.runtime.version",
    "trace_id",
    "span_id",
    "parent_span_id",
    "code.namespace",
    "code.function",
    "code.filepath",
    "code.lineno",
    "exception.type",
    "exception.message",
    "thread.name",
    "thread.id",
    "durationMs",
    "nt.entryType",
    "nt.eventType",
    "nt.schemaVersion",
    "nt.traceName",
    "nt.storyId",
    "nt.chapterId",
    "nt.outcome",
    "nt.forkId",
    "nt.branchIndex",
    "nt.causalId",
    "nt.threadVirtual",
    "nt.package",
    "nt.exceptionPackage",
    "nt.returnType",
    "nt.instanceId",
    "nt.narrationTemplate",
    "nt.returnValue",
    "nt.parameters",
)
EVENT_TYPES = {"method_enter", "method_exit", "fork", "join", "async_dispatch"}
LEVELS = {"trace", "debug", "info", "warn", "error"}

_text = st.text(max_size=20)
_hex32 = st.text(alphabet="0123456789abcdef", min_size=32, max_size=32)
_hex16 = st.text(alphabet="0123456789abcdef", min_size=16, max_size=16)
_nanos = st.integers(min_value=0, max_value=10**15)


@st.composite
def _spans(draw: st.DrawFn) -> SpanContext:
    return SpanContext(
        trace_id=TraceId(draw(_hex32)),
        span_id=SpanId(draw(_hex16)),
        parent_span_id=draw(st.one_of(st.none(), _hex16.map(SpanId))),
        service_name=draw(st.one_of(st.none(), _text)),
        environment=draw(st.one_of(st.none(), _text)),
        span_name=draw(st.one_of(st.none(), _text)),
        story_id=draw(st.one_of(st.none(), _text)),
        chapter_id=draw(st.one_of(st.none(), _text)),
    )


@st.composite
def _outcomes(draw: st.DrawFn) -> TraceOutcome:
    kind = draw(st.sampled_from(["returned", "void", "threw", "incomplete"]))
    if kind == "returned":
        return Returned(draw(_text))
    if kind == "void":
        return Returned(None)
    if kind == "threw":
        return Threw(ValueError(draw(_text)))
    return Incomplete()


@st.composite
def _events(draw: st.DrawFn) -> TraceEvent:
    kind = draw(st.sampled_from(["enter", "exit", "fork", "merge", "fire"]))
    nanos = draw(_nanos)
    if kind == "enter":
        params = draw(
            st.lists(st.builds(ParameterCapture, _text, _text, st.booleans()), max_size=3)
        )
        return EnterEvent(draw(_spans()), nanos, MethodSignature(draw(_text), draw(_text), params))
    if kind == "exit":
        return ExitEvent(draw(_spans()), nanos, draw(_outcomes()))
    if kind == "fork":
        return ForkCreatedEvent(draw(_text), nanos)
    if kind == "merge":
        return MergeEvent(draw(_text), draw(st.integers(0, 5)), nanos)
    return FireAndForgetEvent(draw(_text), nanos)


def _doc(event: TraceEvent) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(entry_to_json(entry_from_event(event, anchor=ANCHOR)))
    return doc


@given(_events())
def test_every_event_maps_to_a_schema_shaped_entry(event: TraceEvent) -> None:
    entry = entry_from_event(event, anchor=ANCHOR)
    assert entry.nt_entry_type == "entry"
    assert entry.nt_schema_version == SCHEMA_VERSION
    assert entry.nt_event_type in EVENT_TYPES
    assert entry.level in LEVELS


@given(_events())
def test_the_wire_form_never_emits_a_null_value(event: TraceEvent) -> None:
    assert all(value is not None for value in _doc(event).values())


@given(_events())
def test_emitted_keys_are_always_a_subsequence_of_the_canonical_order(event: TraceEvent) -> None:
    keys = list(_doc(event))
    positions = [CANONICAL_ORDER.index(key) for key in keys]
    assert positions == sorted(positions)
    assert len(set(keys)) == len(keys)


@given(_events())
def test_the_document_and_json_forms_agree(event: TraceEvent) -> None:
    entry = entry_from_event(event, anchor=ANCHOR)
    assert json.loads(entry_to_json(entry)) == json.loads(json.dumps(entry_document(entry)))


@given(_events())
def test_error_level_holds_exactly_when_the_outcome_failed(event: TraceEvent) -> None:
    entry = entry_from_event(event, anchor=ANCHOR)
    assert (entry.level == "error") == (entry.nt_outcome == "failure")


@given(_events())
def test_exception_fields_appear_exactly_on_failures(event: TraceEvent) -> None:
    entry = entry_from_event(event, anchor=ANCHOR)
    assert (entry.exception_type is not None) == (entry.nt_outcome == "failure")


@given(st.lists(_nanos, min_size=2, max_size=2))
def test_timestamps_never_go_backwards_as_readings_advance(readings: list[int]) -> None:
    earlier, later = sorted(readings)
    assert ANCHOR.timestamp(earlier) <= ANCHOR.timestamp(later)
