# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the TraceEvent union and span_id_of."""

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.events import (
    EnterEvent,
    ExitEvent,
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
    TraceEvent,
    span_id_of,
)
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

CTX = SpanContext(trace_id=TraceId("a" * 32), span_id=SpanId("b" * 16))
SIG = MethodSignature("C", "m", [])


def test_enter_event_defaults_concurrency_to_none() -> None:
    event = EnterEvent(CTX, 100, SIG)
    assert event.concurrency is None
    assert event.timestamp_nanos == 100


def test_enter_event_with_concurrency() -> None:
    info = ConcurrencyInfo("g", ConcurrencyKind.FORK_JOIN)
    assert EnterEvent(CTX, 100, SIG, info).concurrency is info


def test_exit_event_defaults_error_context_to_none() -> None:
    event = ExitEvent(CTX, 200, Returned("x"))
    assert event.error_context is None


def test_span_id_of_enter_and_exit() -> None:
    assert span_id_of(EnterEvent(CTX, 100, SIG)) == CTX.span_id
    assert span_id_of(ExitEvent(CTX, 200, Returned("x"))) == CTX.span_id


def test_span_id_of_group_events_is_none() -> None:
    assert span_id_of(ForkCreatedEvent("g", 1)) is None
    assert span_id_of(MergeEvent("g", 2, 1)) is None
    assert span_id_of(FireAndForgetEvent("g", 1)) is None


def test_variants_are_trace_events() -> None:
    events: list[TraceEvent] = [
        EnterEvent(CTX, 1, SIG),
        ExitEvent(CTX, 2, Returned("x")),
        ForkCreatedEvent("g", 1),
        MergeEvent("g", 1, 1),
        FireAndForgetEvent("g", 1),
    ]
    assert all(isinstance(e, TraceEvent) for e in events)
