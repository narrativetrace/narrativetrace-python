# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for BufferedEventConsumer: draining, subscribers, backpressure, watchdog."""

from __future__ import annotations

import asyncio
import concurrent.futures
import gc
import inspect
import threading
import time
import weakref

import pytest

from narrativetrace.events import EnterEvent, ExitEvent, TraceEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.outcomes import Returned, TraceOutcome
from narrativetrace.pipeline.buffered_consumer import (
    DEFAULT_CAPACITY,
    BufferedEventConsumer,
    _atexit_close,
    _Watchdog,
)
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

TRACE = TraceId("a" * 32)


def _span(hex6: str) -> SpanContext:
    return SpanContext(trace_id=TRACE, span_id=SpanId(hex6.ljust(16, "0")))


def _enter(hex6: str, name: str = "run") -> EnterEvent:
    return EnterEvent(_span(hex6), 0, MethodSignature("Svc", name, []))


def _exit(hex6: str, outcome: TraceOutcome) -> ExitEvent:
    return ExitEvent(_span(hex6), 10, outcome)


class _Clock:
    def __init__(self) -> None:
        self.now = 1

    def __call__(self) -> int:
        return self.now


class TestDraining:
    def test_flush_makes_events_visible(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        c.accept(_enter("a"))
        c.accept(_exit("a", Returned("x")))
        assert c.events() == []  # not drained yet
        c.flush()
        assert len(c.events()) == 2

    def test_clear_empties_store(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        c.accept(_enter("a"))
        c.flush()
        c.clear()
        assert c.events() == []

    def test_remove_spans(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        c.accept(_enter("a"))
        c.accept(_enter("b"))
        c.flush()
        c.remove_spans({SpanId("a".ljust(16, "0"))})
        remaining = {e.span_context.span_id for e in c.events() if isinstance(e, EnterEvent)}
        assert remaining == {SpanId("b".ljust(16, "0"))}

    def test_drain_thread_processes_and_flush_completes(self) -> None:
        c = BufferedEventConsumer(start_consumer=True)
        try:
            for i in range(20):
                c.accept(_enter(format(i + 1, "x")))
            c.flush()
            assert len(c.events()) == 20  # each event processed exactly once
        finally:
            c.close()


class TestSubscribers:
    def test_fanout_to_multiple_subscribers(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        a: list[TraceEvent] = []
        b: list[TraceEvent] = []
        c.subscribe(a.append)
        c.subscribe(b.append)
        c.accept(_enter("a"))
        c.flush()
        assert len(a) == 1
        assert len(b) == 1

    def test_throwing_subscriber_isolated(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        good: list[TraceEvent] = []

        def boom(_event: TraceEvent) -> None:
            raise RuntimeError("subscriber broke")

        c.subscribe(boom)
        c.subscribe(good.append)
        c.accept(_enter("a"))
        c.flush()  # must not raise
        assert len(good) == 1  # other subscriber still received it
        assert c.dropped_count() == 0  # a throw is not a backpressure drop
        assert len(c.events()) == 1  # store still received it

    def test_a_subscriber_raising_a_non_exception_baseexception_is_isolated(self) -> None:
        """Mirrors a Java bug-hunt finding ("catches Exception, not Throwable"): a subscriber
        whose failure is not an ``Exception`` subclass must not stall the drain thread or its
        neighbours either — this runtime's own addendum names this exact gap for Python's exception
        hierarchy.
        """
        c = BufferedEventConsumer(start_consumer=False)
        good: list[TraceEvent] = []

        class Boom(BaseException):
            pass

        def boom(_event: TraceEvent) -> None:
            raise Boom("subscriber broke with a non-Exception BaseException")

        c.subscribe(boom)
        c.subscribe(good.append)
        c.accept(_enter("a"))
        c.flush()  # must not raise
        assert len(good) == 1

    def test_a_subscriber_raising_cancelled_error_still_propagates(self) -> None:
        """Cancellation is exempt from the isolation above and must still propagate, matching
        every other best-effort boundary in this runtime (see narrativetrace._boundary).
        """
        c = BufferedEventConsumer(start_consumer=False)

        def cancelling(_event: TraceEvent) -> None:
            raise asyncio.CancelledError("cancelled")

        slot = c.subscribe(cancelling)
        c.accept(_enter("a"))
        with pytest.raises(asyncio.CancelledError):
            c.flush()

        assert slot.busy is False  # must not be left stuck busy, dropping every future event

    def test_slow_async_subscriber_drops_while_busy(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        pending: list[concurrent.futures.Future[None]] = []

        def slow(_event: TraceEvent) -> concurrent.futures.Future[None]:
            fut: concurrent.futures.Future[None] = concurrent.futures.Future()
            pending.append(fut)
            return fut

        slot = c.subscribe(slow)
        c.accept(_enter("a"))
        c.accept(_enter("b"))
        c.flush()  # first delivery starts (busy), second is dropped
        assert slot.dropped == 1
        pending[0].set_result(None)  # subscriber frees up
        c.accept(_enter("c"))
        c.flush()
        assert slot.dropped == 1  # no further drop once free


class TestWatchdog:
    def test_stale_since_millis_zero_before_activity(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        assert c.stale_since_millis() == 0

    def test_stale_since_millis_after_activity(self) -> None:
        clock = _Clock()
        c = BufferedEventConsumer(start_consumer=False, clock=clock)
        clock.now = 1_000_000  # 1ms baseline
        c._drain_cycle()  # records last_activity
        clock.now = 1_000_000 + 7_000_000  # +7ms
        assert c.stale_since_millis() == 7

    def test_watchdog_callback_fires_when_stale(self) -> None:
        clock = _Clock()
        stale: list[int] = []
        c = BufferedEventConsumer(start_consumer=False, clock=clock, on_stale=stale.append)
        clock.now = 1
        c._last_activity_nanos = 1
        clock.now = 1 + 6_000_000_000  # 6s later > 5s threshold
        watchdog = object.__new__(_Watchdog)
        watchdog._consumer_ref = weakref.ref(c)
        watchdog.check()
        assert stale == [6000]

    def test_a_hostile_on_stale_callback_does_not_kill_the_watchdog_thread(self) -> None:
        """Mirrors Java's ``ConsumerWatchdog`` totality guard (a bug-hunt finding): the previous
        code path had no guard at all around ``on_stale`` — any exception, not just a
        non-``Exception`` one, would have propagated out of ``check()`` and stopped the real
        watchdog thread's run loop permanently.
        """
        clock = _Clock()

        class Boom(BaseException):
            pass

        def hostile(_ms: int) -> None:
            raise Boom("watchdog callback must not kill the watchdog thread")

        c = BufferedEventConsumer(start_consumer=False, clock=clock, on_stale=hostile)
        clock.now = 1
        c._last_activity_nanos = 1
        clock.now = 1 + 6_000_000_000
        watchdog = object.__new__(_Watchdog)
        watchdog._consumer_ref = weakref.ref(c)
        assert watchdog.check() is True  # survived; still reports the consumer as alive

    def test_check_returns_false_once_the_consumer_is_gone(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        watchdog = object.__new__(_Watchdog)
        watchdog._consumer_ref = weakref.ref(c)
        del c
        gc.collect()
        assert watchdog.check() is False


class TestClose:
    def test_close_is_idempotent(self) -> None:
        c = BufferedEventConsumer(start_consumer=True)
        c.close()
        c.close()  # must not raise

    def test_atexit_flush_noop_after_close(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        c.accept(_enter("a"))
        c.close()
        c.close()
        assert True

    def test_atexit_close_flushes_a_still_alive_consumer(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        c.accept(_enter("a"))

        _atexit_close(weakref.ref(c))

        assert len(c.events()) == 1
        assert c._closed is True

    def test_atexit_close_is_a_noop_once_the_consumer_is_already_gone(self) -> None:
        dead_ref = weakref.ref(BufferedEventConsumer(start_consumer=False))
        gc.collect()
        assert dead_ref() is None

        _atexit_close(dead_ref)  # must not raise

    def test_accept_after_close_is_not_silently_lost(self) -> None:
        """Stress-mirror invariant 5 (close racing publish: nothing lost uncounted). A caller can
        still be mid-``accept()`` when something else closes the consumer (e.g. shutdown racing
        an in-flight request); the drain thread that would otherwise pick the event up from the
        buffer is already gone once ``close()`` has returned, so the event must not simply sit in
        an abandoned buffer forever, invisible to both ``events()`` and ``dropped_count()``."""
        c = BufferedEventConsumer(start_consumer=True)
        c.close()

        c.accept(_enter("1a7e"))

        assert len(c.events()) + c.dropped_count() == 1


class TestDefaults:
    def test_default_capacity_is_2_to_the_16(self) -> None:
        """Owner contract, 2026-08-31: default cap 65,536 (2^16), cross-runtime."""
        assert DEFAULT_CAPACITY == 1 << 16


class TestConfigurableKnobs:
    """Owner contract, 2026-08-31 (revised): the buffer is fixed-size and never grows; the only
    configurable knobs are capacity and drain interval. There is no initial-capacity knob --
    allocation timing is an implementation detail, never a public option."""

    def test_capacity_is_configurable(self) -> None:
        c = BufferedEventConsumer(start_consumer=False, buffer_capacity=2048)
        assert c._buffer.capacity == 2048

    def test_drain_interval_is_configurable(self) -> None:
        c = BufferedEventConsumer(start_consumer=False, drain_interval_seconds=0.5)
        assert c.drain_interval_seconds == 0.5

    def test_drain_interval_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="drain_interval_seconds"):
            BufferedEventConsumer(start_consumer=False, drain_interval_seconds=0.0)

    def test_constructor_accepts_exactly_capacity_and_drain_interval_as_sizing_knobs(self) -> None:
        """Pins the revised contract: no `initial_capacity` parameter exists at all."""
        params = inspect.signature(BufferedEventConsumer.__init__).parameters
        assert "initial_capacity" not in params
        assert "buffer_capacity" in params
        assert "drain_interval_seconds" in params

    def test_initial_capacity_keyword_is_no_longer_accepted(self) -> None:
        with pytest.raises(TypeError):
            BufferedEventConsumer(start_consumer=False, initial_capacity=2048)  # type: ignore[call-arg]


class TestResourceSafety:
    """Owner contract, 2026-08-31: close() is retained but defaults must be safe without it --
    an abandoned, un-closed consumer must not root itself forever through its own background
    threads. Verified red first: before the fix, neither the drain thread nor the watchdog ever
    released their strong reference to the consumer, so it (and both threads) lived for the rest
    of the process regardless of close() never being called."""

    def _wait_until(self, predicate: object, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            gc.collect()
            if predicate():  # type: ignore[operator]
                return True
            time.sleep(0.01)
        return False

    def test_an_unclosed_consumer_is_eventually_collectible(self) -> None:
        c = BufferedEventConsumer(start_consumer=True, drain_interval_seconds=0.001)
        ref = weakref.ref(c)
        del c

        assert self._wait_until(lambda: ref() is None), "an abandoned consumer must be collected"

    def test_an_unclosed_consumers_drain_thread_stops_itself(self) -> None:
        c = BufferedEventConsumer(start_consumer=True, drain_interval_seconds=0.001)
        thread = c._thread
        assert thread is not None
        del c

        assert self._wait_until(lambda: not thread.is_alive())

    def test_an_unclosed_consumers_watchdog_thread_stops_itself(self) -> None:
        c = BufferedEventConsumer(start_consumer=False)
        watchdog = _Watchdog(c, check_seconds=0.01)  # fast interval, keeps the test quick
        thread = watchdog._thread
        del c

        assert self._wait_until(lambda: not thread.is_alive())

    def test_daemon_threads_never_block_interpreter_exit(self) -> None:
        c = BufferedEventConsumer(start_consumer=True)
        assert c._thread is not None
        assert c._thread.daemon is True
        assert c._watchdog is not None
        assert c._watchdog._thread.daemon is True
        c.close()

    def test_closing_still_works_after_the_leak_fix(self) -> None:
        c = BufferedEventConsumer(start_consumer=True)
        c.accept(_enter("a"))
        c.close()
        assert len(c.events()) == 1
        assert not c._thread.is_alive()  # type: ignore[union-attr]
        assert not c._watchdog._thread.is_alive()  # type: ignore[union-attr]


class TestShedding:
    def test_drains_and_discards_under_load(self) -> None:
        c = BufferedEventConsumer(buffer_capacity=10, start_consumer=False)
        # fill above 70% so a drain cycle sheds (drops) instead of storing
        for i in range(8):
            c.accept(_enter(format(i + 1, "x")))
        c._drain_cycle()
        assert c.events() == []  # shed: nothing was stored
        assert c._buffer.is_empty()  # but the buffer was drained
        assert c.dropped_count() == 8  # and the shed events are counted as loss

    def test_two_separate_shedding_cycles_accumulate_rather_than_replace(self) -> None:
        """Guards the accumulator itself: a second shed must add to the first, not overwrite it."""
        c = BufferedEventConsumer(buffer_capacity=10, start_consumer=False)
        for i in range(8):
            c.accept(_enter(format(i, "x")))
        c._drain_cycle()  # sheds 8
        for i in range(8):
            c.accept(_enter(format(i + 8, "x")))
        c._drain_cycle()  # sheds 8 more
        assert c.dropped_count() == 16


class TestLossAccounting:
    """Mirrors a Java bug-hunt finding: ``dropped_count()`` must count every channel that can
    make the retained event count smaller than what was published — a bounded buffer overwriting
    its ring, and a drain cycle shedding under load — not only per-subscriber backpressure drops.
    Java's own repro shape: 64 events into a 16-capacity ring reports 0 dropped
    before the fix; the invariant a caller relies on is ``retained + dropped_count() == published``.
    """

    def test_a_ring_overwrite_is_counted_as_a_drop(self) -> None:
        c = BufferedEventConsumer(buffer_capacity=16, start_consumer=False)
        for i in range(64):
            c.accept(_enter(format(i, "x")))
        c.flush()
        assert len(c.events()) == 16
        assert c.dropped_count() == 48
        assert len(c.events()) + c.dropped_count() == 64

    def test_retained_plus_dropped_equals_published_with_no_overflow(self) -> None:
        """The invariant holds trivially (dropped == 0) when nothing overflows either channel."""
        c = BufferedEventConsumer(buffer_capacity=64, start_consumer=False)
        for i in range(10):
            c.accept(_enter(format(i, "x")))
        c.flush()
        assert len(c.events()) == 10
        assert c.dropped_count() == 0

    def test_shedding_and_ring_overwrite_drops_both_count_toward_the_same_total(self) -> None:
        c = BufferedEventConsumer(buffer_capacity=10, start_consumer=False)
        for i in range(8):  # above 70% fill: the next drain cycle sheds
            c.accept(_enter(format(i, "x")))
        c._drain_cycle()  # sheds all 8
        for i in range(20):  # now overflow the ring on top of the prior shed
            c.accept(_enter(format(i + 8, "x")))
        c.flush()
        assert c.dropped_count() == 8 + (20 - 10)  # shed + ring-overwritten


class TestCapturePendingEvent:
    """Mirrors a Java bug-hunt finding ("capture read its own writes too early"): a
    ``flush()``/capture must not omit events a producer has already published just because the
    drain has not caught up yet — 2 runs in 8 lost 17-21 of 512 worker spans in Java's own
    fork/fan-out probe, uncounted.

    This runtime's equivalent buffer (``BoundedEventBuffer``) has no analog to the race that caused
    it: Java's lock-free MPSC ring let a producer advance past a slot before finishing the write
    into it, so a reader could see the advance without the data — a "claimed but not yet written"
    state. ``BoundedEventBuffer.put()`` is a single lock-guarded ``deque.append()`` of an event
    the caller has already fully constructed; there is no intermediate state for a concurrent
    ``drain()``/``flush()`` to observe; either the whole append has happened (the lock guarantees
    it) or it has not started. A single ``flush()`` is therefore always sufficient, and this pins
    that architectural fact under real concurrent load rather than a hostile-input repro.
    """

    def test_a_single_flush_after_concurrent_publishers_join_loses_nothing(self) -> None:
        published = 512
        worker_count = 8
        per_worker = published // worker_count
        c = BufferedEventConsumer(buffer_capacity=published * 2, start_consumer=True)

        def publish(base: int) -> None:
            for i in range(base, base + per_worker):
                c.accept(_enter(format(i, "x")))

        threads = [
            threading.Thread(target=publish, args=(i * per_worker,)) for i in range(worker_count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        c.flush()
        retained = len(c.events())
        c.close()

        assert retained + c.dropped_count() == published
