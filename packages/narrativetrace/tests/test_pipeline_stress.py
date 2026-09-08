# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Concurrency stress suite for the ring buffer, buffered consumer, and event store.

Covers the same concurrency scenarios as the Java runtime's jcstress suite (module
``narrativetrace-jcstress``), in this runtime's own idiom: the INVARIANTS are the
cross-runtime contract, jcstress is a JVM-only tool. jcstress schedules interleavings by exhaustive
JVM-level exploration; CPython has no equivalent, so every thread-based test here instead runs many
repetitions of a barrier-synchronised race with the GIL's switch interval lowered (more preemption
points per second). See :mod:`stress_support` for the two-mode (quick/long) repetition budget and
``documentation/concurrency-stress.md`` for the invariant table.

Invariant 3 (lazy ring allocation races allocate exactly once) is structurally N/A for this runtime,
the same as it is for the shared master copy: neither :class:`BoundedEventBuffer`
(``bounded_buffer.py:31-34``) nor :class:`BufferedEventConsumer` (``buffered_consumer.py:80-105``)
allocate anything lazily — the ring, the store, and the drain thread are all built eagerly inside
``__init__``, before the constructed object is ever handed to a caller who could race a second
thread against it. There is no "does the first publish race the allocation?" question to ask of
this design — the same substitution Java's own suite makes in ``UnsafePublicationTest``'s Javadoc.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest
from stress_support import narrowed_switch_interval, run_barrier_synced, stress_repeat

from narrativetrace.events import EnterEvent, span_id_of
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.pipeline.bounded_buffer import BoundedEventBuffer
from narrativetrace.pipeline.buffered_consumer import BufferedEventConsumer
from narrativetrace.pipeline.event_store import EventStore
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

pytestmark = pytest.mark.stress

_TRACE = TraceId.generate()


def _enter(span_id: SpanId) -> EnterEvent:
    signature = MethodSignature("Svc", "run", [])
    return EnterEvent(SpanContext(trace_id=_TRACE, span_id=span_id), 0, signature)


def _tagged_span_id(tag: int) -> SpanId:
    """Encodes a sequence number directly as the span id's hex value, so a reader can recover
    publish order from the event alone (mirrors Java's ``StressEvents`` tagging helper)."""
    return SpanId(f"{tag:016x}")


def _tag_of(span_id: SpanId) -> int:
    return int(span_id.value, 16)


# --------------------------------------------------------------------------- #
# Invariant 1 — loss accounting is exact                                       #
# --------------------------------------------------------------------------- #
def _producer(
    consumer: BufferedEventConsumer, sink: list[SpanId], count: int
) -> Callable[[], None]:
    def produce() -> None:
        for _ in range(count):
            span_id = SpanId.generate()
            sink.append(span_id)
            consumer.accept(_enter(span_id))

    return produce


def _loss_accounting_iteration(worker_count: int, per_worker: int, capacity: int) -> None:
    consumer = BufferedEventConsumer(buffer_capacity=capacity, start_consumer=True)
    published: list[list[SpanId]] = [[] for _ in range(worker_count)]
    producers = [_producer(consumer, published[i], per_worker) for i in range(worker_count)]
    with narrowed_switch_interval():
        run_barrier_synced(producers)
    consumer.close()

    all_published = {sid for ids in published for sid in ids}
    assert len(all_published) == worker_count * per_worker  # SpanId.generate() never collides
    stored = [span_id_of(e) for e in consumer.events()]
    assert len(set(stored)) == len(stored)  # no duplicate delivery
    assert set(stored) <= all_published  # nothing delivered that was never published
    assert len(stored) + consumer.dropped_count() == len(all_published)


class TestLossAccountingExact:
    """Invariant 1: delivered + shed(+overwritten) == published, under any interleaving; no event
    is ever both counted-as-shed and delivered."""

    def test_small_ring_under_heavy_concurrent_publish(self) -> None:
        for _ in range(stress_repeat(quick=5, long=200)):
            _loss_accounting_iteration(worker_count=6, per_worker=40, capacity=16)

    def test_ring_with_spare_capacity_loses_nothing(self) -> None:
        for _ in range(stress_repeat(quick=5, long=100)):
            _loss_accounting_iteration(worker_count=4, per_worker=20, capacity=4096)


# --------------------------------------------------------------------------- #
# Invariant 2 — no torn/partial reads                                          #
# --------------------------------------------------------------------------- #
def _assert_valid_prefix(store: EventStore) -> int:
    tags = [_tag_of(span_id_of(e)) for e in store.events()]  # type: ignore[arg-type]
    assert tags == list(range(len(tags)))  # exactly the first len(tags) appends, in order
    return len(tags)


def _event_store_snapshot_iteration(event_count: int) -> None:
    store = EventStore()
    done = threading.Event()
    snapshot_lengths: list[int] = []
    with narrowed_switch_interval():
        run_barrier_synced(
            [
                _append_tagged(store, event_count, done),
                _sample_prefixes(store, done, snapshot_lengths),
            ]
        )
    assert snapshot_lengths[-1] == event_count
    assert snapshot_lengths == sorted(snapshot_lengths)  # each snapshot only grows


def _append_tagged(
    store: EventStore, event_count: int, done: threading.Event
) -> Callable[[], None]:
    def append_all() -> None:
        for tag in range(event_count):
            store.add(_enter(_tagged_span_id(tag)))
        done.set()

    return append_all


def _sample_prefixes(
    store: EventStore, done: threading.Event, sink: list[int]
) -> Callable[[], None]:
    def sample_until_done() -> None:
        while not done.is_set():
            sink.append(_assert_valid_prefix(store))
        sink.append(_assert_valid_prefix(store))

    return sample_until_done


def _bounded_buffer_drain_race_iteration(event_count: int, capacity: int) -> None:
    buffer = BoundedEventBuffer(capacity)
    done = threading.Event()
    delivered: list[int] = []
    with narrowed_switch_interval():
        run_barrier_synced(
            [_produce_tagged(buffer, event_count, done), _drain_tagged(buffer, done, delivered)]
        )
    assert delivered == sorted(delivered)  # a genuine subsequence, never reordered
    assert len(set(delivered)) == len(delivered)  # never delivered twice
    assert len(delivered) + buffer.overwritten_count() == event_count


def _produce_tagged(
    buffer: BoundedEventBuffer, event_count: int, done: threading.Event
) -> Callable[[], None]:
    def produce() -> None:
        for tag in range(event_count):
            buffer.put(_enter(_tagged_span_id(tag)))
        done.set()

    return produce


def _drain_tagged(
    buffer: BoundedEventBuffer, done: threading.Event, sink: list[int]
) -> Callable[[], None]:
    def consume() -> None:
        while not (done.is_set() and buffer.is_empty()):
            event = buffer.poll()
            if event is not None:
                sink.append(_tag_of(span_id_of(event)))  # type: ignore[arg-type]

    return consume


class TestNoTornReads:
    """Invariant 2: a drain or snapshot sees prefix-consistent state, never a half-written slot
    or a partially visible append."""

    def test_event_store_snapshots_are_always_a_valid_prefix_while_appends_race(self) -> None:
        for _ in range(stress_repeat(quick=5, long=150)):
            _event_store_snapshot_iteration(event_count=300)

    def test_bounded_buffer_drain_racing_publish_never_reorders_or_corrupts(self) -> None:
        for _ in range(stress_repeat(quick=5, long=150)):
            _bounded_buffer_drain_race_iteration(event_count=400, capacity=8)


# --------------------------------------------------------------------------- #
# Invariant 4 — the tail is never stranded                                     #
# --------------------------------------------------------------------------- #
def _lands_within(consumer: BufferedEventConsumer, span_id: SpanId, bound_seconds: float) -> bool:
    deadline = time.monotonic() + bound_seconds
    while time.monotonic() < deadline:
        if any(span_id_of(e) == span_id for e in consumer.events()):
            return True
    return False


class TestTailNeverStranded:
    """Invariant 4: a publish into an empty buffer around the drain thread's idle-park moment is
    always eventually drained (the timer/thread-wake-up race)."""

    def test_publish_into_an_idle_consumer_always_lands_within_a_bounded_time(self) -> None:
        bound_seconds = 0.5
        for _ in range(stress_repeat(quick=10, long=300)):
            consumer = BufferedEventConsumer(
                buffer_capacity=64, start_consumer=True, drain_interval_seconds=0.001
            )
            try:
                time.sleep(0.002)  # let the drain thread settle into its idle wait
                span_id = SpanId.generate()
                consumer.accept(_enter(span_id))
                landed = _lands_within(consumer, span_id, bound_seconds)
                assert landed, "publish into an idle drain thread was stranded past the bound"
            finally:
                consumer.close()


# --------------------------------------------------------------------------- #
# Invariant 5 — close()/dispose() racing publish and flush                     #
# --------------------------------------------------------------------------- #
def _close_race_iteration(capacity: int, per_worker: int) -> None:
    consumer = BufferedEventConsumer(buffer_capacity=capacity, start_consumer=True)
    published: list[SpanId] = []
    published_lock = threading.Lock()

    def publish() -> None:
        for _ in range(per_worker):
            span_id = SpanId.generate()
            with published_lock:
                published.append(span_id)
            consumer.accept(_enter(span_id))

    with narrowed_switch_interval():
        run_barrier_synced([publish, consumer.flush, consumer.close, consumer.close])
    consumer.close()  # a third, sequential close after the race: still idempotent, no double drain

    stored = [span_id_of(e) for e in consumer.events()]
    assert len(set(stored)) == len(stored)  # no duplicate delivery from the racing closers
    assert len(stored) + consumer.dropped_count() == len(published)


class TestCloseRacingPublishAndFlush:
    """Invariant 5: close()/dispose() racing publish and flush is idempotent, nothing is lost
    silently uncounted, and the drain mechanism terminates."""

    def test_two_concurrent_closers_race_a_publisher_and_a_flusher(self) -> None:
        for _ in range(stress_repeat(quick=8, long=200)):
            _close_race_iteration(capacity=32, per_worker=60)

    def test_publish_racing_a_single_close_on_a_roomy_ring_always_delivers(self) -> None:
        """The narrow case Java's ``CloseRacingPublishTest`` pins directly: with no capacity
        pressure, nothing should ever be dropped — every race outcome is delivery, never loss.

        Regression proof for a real defect this suite found: ``accept()`` after ``close()`` used
        to sit in the abandoned buffer forever, invisible to both ``events()`` and
        ``dropped_count()`` (see the deterministic pin in
        ``test_pipeline_buffered.py::TestClose::test_accept_after_close_is_not_silently_lost``
        and the fix in ``buffered_consumer.py``'s ``accept()``).
        """
        for _ in range(stress_repeat(quick=10, long=300)):
            consumer = BufferedEventConsumer(buffer_capacity=4096, start_consumer=True)
            span_id = SpanId.generate()
            with narrowed_switch_interval():
                run_barrier_synced([_accept_once(consumer, span_id), consumer.close])
            consumer.close()
            stored = [span_id_of(e) for e in consumer.events()]
            assert stored == [span_id]  # the only acceptable outcome: always delivered
            assert consumer.dropped_count() == 0


def _accept_once(consumer: BufferedEventConsumer, span_id: SpanId) -> Callable[[], None]:
    def accept() -> None:
        consumer.accept(_enter(span_id))

    return accept


# --------------------------------------------------------------------------- #
# Invariant 6 — flush()'s post-condition under concurrent publish              #
# --------------------------------------------------------------------------- #
class TestFlushPostConditionUnderConcurrentPublish:
    """Invariant 6: everything published-before a flush-to-quiescence is in the store after —
    formalises the "30 manual attempts" this runtime already ran for a bug-hunt finding into a
    repeatable, seeded stress harness."""

    def test_flush_after_concurrent_publishers_join_loses_nothing(self) -> None:
        published = 512
        worker_count = 8
        per_worker = published // worker_count
        for _ in range(stress_repeat(quick=5, long=100)):
            consumer = BufferedEventConsumer(buffer_capacity=published * 2, start_consumer=True)
            producers = [_producer(consumer, [], per_worker) for _ in range(worker_count)]
            with narrowed_switch_interval():
                run_barrier_synced(producers)
            consumer.flush()
            retained = len(consumer.events())
            consumer.close()
            assert retained + consumer.dropped_count() == published
