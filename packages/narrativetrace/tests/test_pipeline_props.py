# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for pipeline invariants."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from narrativetrace.events import EnterEvent, ExitEvent, TraceEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.outcomes import Returned
from narrativetrace.pipeline.buffered_consumer import BufferedEventConsumer
from narrativetrace.pipeline.dual_path import DualPathPipeline
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

TRACE = TraceId("a" * 32)


def _events(n: int) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for i in range(n):
        ctx = SpanContext(trace_id=TRACE, span_id=SpanId(format(i + 1, "016x")))
        events.append(EnterEvent(ctx, i * 2, MethodSignature("Svc", "m", [])))
        events.append(ExitEvent(ctx, i * 2 + 1, Returned("x")))
    return events


@given(st.integers(min_value=0, max_value=50))
def test_event_count_conserved_through_consumer(n: int) -> None:
    consumer = BufferedEventConsumer(start_consumer=False)
    events = _events(n)
    for event in events:
        consumer.accept(event)
    consumer.flush()
    assert len(consumer.events()) == len(events)


@given(st.integers(min_value=0, max_value=50))
def test_order_preserved_single_producer(n: int) -> None:
    consumer = BufferedEventConsumer(start_consumer=False)
    events = _events(n)
    for event in events:
        consumer.accept(event)
    consumer.flush()
    assert consumer.events() == events


@given(st.lists(st.booleans(), min_size=0, max_size=20))
def test_no_crash_under_random_subscriber_failures(failures: list[bool]) -> None:
    # A pipeline whose sync listener randomly throws never propagates to the publisher.
    calls = iter(failures)

    def flaky(_event: TraceEvent) -> None:
        if next(calls, False):
            raise RuntimeError("boom")

    pipeline = DualPathPipeline(flaky)
    for event in _events(len(failures)):
        pipeline.publish(event)  # must never raise
