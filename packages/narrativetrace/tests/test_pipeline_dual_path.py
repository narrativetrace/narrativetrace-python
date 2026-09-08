# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for DualPathPipeline exception isolation and BoundedEventBuffer."""

from __future__ import annotations

import asyncio

import pytest

from narrativetrace.events import EnterEvent, TraceEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.pipeline.bounded_buffer import BoundedEventBuffer
from narrativetrace.pipeline.buffered_consumer import BufferedEventConsumer
from narrativetrace.pipeline.dual_path import DualPathPipeline
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

TRACE = TraceId("a" * 32)


def _event(hex_char: str) -> EnterEvent:
    ctx = SpanContext(trace_id=TRACE, span_id=SpanId(hex_char * 16))
    return EnterEvent(ctx, 0, MethodSignature("Svc", "m", []))


class _Recorder:
    def __init__(self) -> None:
        self.received: list[TraceEvent] = []

    def accept(self, event: TraceEvent) -> None:
        self.received.append(event)


class TestDualPathIsolation:
    def test_throwing_sync_listener_does_not_propagate(self) -> None:
        recorder = _Recorder()

        def boom(_event: TraceEvent) -> None:
            raise RuntimeError("listener broke")

        pipeline = DualPathPipeline(boom, recorder)
        pipeline.publish(_event("a"))  # must not raise
        assert len(recorder.received) == 1  # best-effort path still received it

    def test_throwing_best_effort_does_not_propagate(self) -> None:
        seen: list[TraceEvent] = []

        class Boom:
            def accept(self, event: TraceEvent) -> None:
                raise RuntimeError("consumer broke")

        pipeline = DualPathPipeline(seen.append, Boom())
        pipeline.publish(_event("a"))  # must not raise
        assert len(seen) == 1  # sync path still received it

    def test_no_paths_is_noop(self) -> None:
        DualPathPipeline().publish(_event("a"))

    def test_a_sync_listener_raising_a_non_exception_baseexception_does_not_propagate(
        self,
    ) -> None:
        """Mirrors a Java bug-hunt finding ("catches Exception, not Throwable"): this runtime's own
        addendum names this exact gap for Python's exception hierarchy.
        """
        recorder = _Recorder()

        class Boom(BaseException):
            pass

        def boom(_event: TraceEvent) -> None:
            raise Boom("listener broke with a non-Exception BaseException")

        pipeline = DualPathPipeline(boom, recorder)
        pipeline.publish(_event("a"))  # must not raise
        assert len(recorder.received) == 1

    def test_a_best_effort_consumer_raising_a_non_exception_baseexception_does_not_propagate(
        self,
    ) -> None:
        seen: list[TraceEvent] = []

        class Boom(BaseException):
            pass

        class HostileConsumer:
            def accept(self, event: TraceEvent) -> None:
                raise Boom("consumer broke with a non-Exception BaseException")

        pipeline = DualPathPipeline(seen.append, HostileConsumer())
        pipeline.publish(_event("a"))  # must not raise
        assert len(seen) == 1

    def test_a_listener_raising_cancelled_error_still_propagates(self) -> None:
        """Cancellation is exempt and must still propagate, matching every other best-effort
        boundary in this runtime (see narrativetrace._boundary)."""

        def cancelling(_event: TraceEvent) -> None:
            raise asyncio.CancelledError("cancelled")

        pipeline = DualPathPipeline(cancelling, _Recorder())
        with pytest.raises(asyncio.CancelledError):
            pipeline.publish(_event("a"))


class TestBoundedBuffer:
    def test_put_poll_fifo(self) -> None:
        buf = BoundedEventBuffer(4)
        buf.put(_event("a"))
        buf.put(_event("b"))
        first = buf.poll()
        assert isinstance(first, EnterEvent)
        assert first.span_context.span_id == SpanId("a" * 16)
        assert buf.poll() is not None
        assert buf.poll() is None

    def test_overflow_drops_oldest(self) -> None:
        buf = BoundedEventBuffer(2)
        buf.put(_event("a"))
        buf.put(_event("b"))
        buf.put(_event("c"))  # capacity 2 → "a" dropped
        assert buf.size() == 2
        remaining = [buf.poll(), buf.poll()]
        ids = {e.span_context.span_id for e in remaining if isinstance(e, EnterEvent)}
        assert SpanId("a" * 16) not in ids

    def test_drain_empties_and_delivers_in_order(self) -> None:
        buf = BoundedEventBuffer(8)
        for c in "abc":
            buf.put(_event(c))
        collected: list[TraceEvent] = []
        buf.drain(collected.append)
        assert len(collected) == 3
        assert buf.is_empty()

    def test_capacity_floor_is_one(self) -> None:
        assert BoundedEventBuffer(0).capacity == 1


class TestStoreDelegation:
    def _pipeline(self) -> tuple[DualPathPipeline, object]:
        consumer = BufferedEventConsumer(start_consumer=False)
        return DualPathPipeline(None, consumer), consumer

    def test_has_store_and_events_flush(self) -> None:
        pipeline, _ = self._pipeline()
        assert pipeline.has_store()
        pipeline.publish(_event("a"))
        assert pipeline.events() == []  # not flushed
        pipeline.flush()
        assert len(pipeline.events()) == 1

    def test_clear(self) -> None:
        pipeline, _ = self._pipeline()
        pipeline.publish(_event("a"))
        pipeline.flush()
        pipeline.clear()
        assert pipeline.events() == []

    def test_clear_spans(self) -> None:
        pipeline, _ = self._pipeline()
        pipeline.publish(_event("a"))
        pipeline.publish(_event("b"))
        pipeline.flush()
        pipeline.clear_spans({SpanId("a" * 16)})
        assert len(pipeline.events()) == 1

    def test_close_delegates(self) -> None:
        pipeline, _ = self._pipeline()
        pipeline.close()  # must not raise

    def test_no_store_variant(self) -> None:
        pipeline = DualPathPipeline(lambda _e: None)
        assert not pipeline.has_store()
        assert pipeline.events() == []
        pipeline.flush()
        pipeline.clear()
        pipeline.clear_spans({SpanId("a" * 16)})
        pipeline.close()
