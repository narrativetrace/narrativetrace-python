# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Best-effort asynchronous consumer backed by a bounded buffer and drain thread.

``BufferedEventConsumer`` / ``ConsumerWatchdog`` / ``DropCountingHandler``. Keeps an
event history without blocking the caller on every publish. Adaptive draining has two modes by
queue fill:

* **normal** (< 70%) — full processing: event store + subscriber fan-out
* **shedding** (>= 70%) — drain and discard without storing (best-effort under load)

(Multi-invocation aggregation and method/error frequency counting were relocated to the paid tier
per Phase 31a, 2026-07-12.)

Python idioms: a daemon :class:`threading.Thread` drains; :func:`atexit` flushes on exit; the
per-subscriber ``dropped_count`` counts backpressure drops (a subscriber still busy with an
async delivery skips the event) — matching the TypeScript runtime's model, closer to the shared
intent than the .NET one (core-pipeline §TS-PIPE-10).

**Cross-runtime buffered-consumer defaults contract (owner, 2026-08-31, revised same day).** Default
cap 65,536 (``2**16``). The buffer is fixed-size and never grows; the only configurable knobs are
capacity and drain interval — there is no initial-capacity knob, because allocation timing is an
implementation detail, never a public option. ``close()`` is retained but the defaults must be safe
without it ever being called; sizing rule for callers: cap is approximately peak events per second
times tolerable drain stall.

Audited against it here: :class:`~narrativetrace.pipeline.bounded_buffer.BoundedEventBuffer` wraps
a :class:`collections.deque`, which happens to grow its backing linked blocks incrementally as items
are appended rather than pre-allocating ``capacity`` slots up front (unlike Java's array-backed ring
buffer). That incremental allocation is exactly the kind of detail the contract puts out of scope —
it is never exposed as a knob, and no constructor parameter names it.

The other half did **not** hold, and was the real finding here: neither the drain thread nor the
watchdog timer released their reference to the consumer, so an un-closed, unreferenced instance —
and both of its background threads — lived for the rest of the process. Both are daemon threads
(never block interpreter exit), but that is a different guarantee from not being *rooted*. Fixed by
holding only a :class:`weakref.ref` to the consumer from both loops and having each stop itself the
first time that reference resolves to nothing, so an abandoned consumer becomes collectible and its
threads terminate rather than polling a dead reference forever.
"""

from __future__ import annotations

import atexit
import concurrent.futures
import threading
import time
import weakref
from collections.abc import Callable

from narrativetrace._boundary import PROPAGATED_EXCEPTIONS
from narrativetrace.events import TraceEvent
from narrativetrace.pipeline.bounded_buffer import BoundedEventBuffer
from narrativetrace.pipeline.event_store import EventStore

DEFAULT_CAPACITY = 1 << 16
_SHEDDING_THRESHOLD = 0.70
_WATCHDOG_STALE_NANOS = 5_000_000_000
_WATCHDOG_CHECK_SECONDS = 1.0
_DEFAULT_DRAIN_INTERVAL_SECONDS = 0.001

_SubscriberCallback = Callable[[TraceEvent], object]


def _validate_knobs(drain_interval_seconds: float) -> None:
    if drain_interval_seconds <= 0:
        raise ValueError("drain_interval_seconds must be positive")


class _SubscriberSlot:
    __slots__ = ("busy", "callback", "dropped")

    def __init__(self, callback: _SubscriberCallback) -> None:
        self.callback = callback
        self.busy = False
        self.dropped = 0


class BufferedEventConsumer:
    """A bounded, drain-threaded, fail-safe best-effort consumer of trace events."""

    def __init__(
        self,
        buffer_capacity: int = DEFAULT_CAPACITY,
        start_consumer: bool = True,
        clock: Callable[[], int] = time.perf_counter_ns,
        on_stale: Callable[[int], None] | None = None,
        drain_interval_seconds: float = _DEFAULT_DRAIN_INTERVAL_SECONDS,
    ) -> None:
        _validate_knobs(drain_interval_seconds)
        self._buffer = BoundedEventBuffer(buffer_capacity)
        self._store = EventStore()
        self._clock = clock
        self._on_stale = on_stale
        self.drain_interval_seconds = drain_interval_seconds
        self._subscribers: list[_SubscriberSlot] = []
        self._subscriber_lock = threading.Lock()
        self._shed_count = 0
        # Serializes whole drain steps (claim from the buffer THROUGH store/shed
        # accounting) against flush(). Without it an event the background cycle has
        # polled but not yet stored — or shed but not yet counted — is invisible to
        # both the buffer and the store, so a concurrent flush() returns while a
        # published event is unaccounted for and invariant 6 (nothing published
        # before a flush is lost uncounted after it) fails. Ordering: _drain_lock
        # is always OUTERMOST; the buffer's and subscribers' locks nest inside.
        self._drain_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._closed = False
        self._running = True
        self._last_activity_nanos = 0
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._watchdog: _Watchdog | None = None
        if start_consumer:
            self._start_background_work(drain_interval_seconds)

    def _start_background_work(self, drain_interval_seconds: float) -> None:
        self._thread = threading.Thread(
            target=_drain_loop,
            args=(weakref.ref(self), self._wake, drain_interval_seconds),
            name="narrative-trace-consumer",
            daemon=True,
        )
        self._thread.start()
        self._watchdog = _Watchdog(self)
        # A bound method here (`self.close`) would be a fourth strong reference keeping an
        # abandoned consumer alive: atexit holds registered callbacks for the life of the
        # process. A weakref keeps atexit's own flush-on-exit behaviour without rooting it.
        atexit.register(_atexit_close, weakref.ref(self))

    # -- ingestion ---------------------------------------------------------- #
    def accept(self, event: TraceEvent) -> None:
        """Enqueues an event (never blocks; overwrites oldest when full).

        A caller can still be mid-``accept()`` when something else closes this consumer — an
        in-flight request racing shutdown. ``close()`` stops the drain thread that would otherwise
        pick this event up, so an event that lands at or after that point is rescued by draining
        it here instead of leaving it in an abandoned buffer forever, invisible to both
        :meth:`events` and :meth:`dropped_count` (stress-mirror invariant 5: close racing publish
        must never lose an event silently, uncounted). Reading ``_closed`` unlocked is safe under
        the GIL — a `close()` that has not yet flipped it will still observe this event through its
        own drain, and `BoundedEventBuffer.drain()`'s lock makes a second, racing rescue drain here
        a safe no-op rather than a double delivery.
        """
        self._buffer.put(event)
        if self._closed:
            self._drain_remaining()

    def subscribe(self, callback: _SubscriberCallback) -> _SubscriberSlot:
        """Registers a fan-out subscriber; returns its slot (for backpressure inspection)."""
        slot = _SubscriberSlot(callback)
        with self._subscriber_lock:
            self._subscribers.append(slot)
        return slot

    # -- queries ------------------------------------------------------------ #
    def events(self) -> list[TraceEvent]:
        return self._store.events()

    def dropped_count(self) -> int:
        """Total events this consumer lost: subscriber backpressure, ring overwrite, and
        shedding (a bug-hunt finding — all three loss channels are counted, or a bounded-buffer
        overflow reports as zero loss while most of the run silently never arrives).
        """
        with self._subscriber_lock:
            subscriber_drops = sum(slot.dropped for slot in self._subscribers)
        return subscriber_drops + self._buffer.overwritten_count() + self._shed_count

    def last_activity_nanos(self) -> int:
        return self._last_activity_nanos

    def stale_since_millis(self) -> int:
        last = self._last_activity_nanos
        if last == 0:
            return 0
        return (self._clock() - last) // 1_000_000

    # -- lifecycle ---------------------------------------------------------- #
    def flush(self) -> None:
        """Drains all buffered events into the store so queries observe them.

        A true barrier: waits for any in-flight background drain step to finish its
        store append (or shed count) before draining the remainder, so everything
        published-before this call is stored or loss-counted after it (invariant 6).
        """
        self._drain_remaining()

    def clear(self) -> None:
        """Clears stored events and aggregate state."""
        self._store.clear()

    def remove_spans(self, span_ids: object) -> None:
        """Removes only stored events for the given span ids (request-scoped cleanup)."""
        self._store.remove_spans(span_ids)  # type: ignore[arg-type]

    def close(self) -> None:
        """Stops the drain thread, flushes remaining events, and unregisters the watchdog.

        Not required for safety: an un-closed consumer that nobody holds a reference to any more
        is still collected, and its background threads still stop themselves. Call this to flush
        deterministically and release the threads promptly instead of waiting on them to notice.
        """
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._running = False
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._watchdog is not None:
            self._watchdog.stop()
        self._drain_remaining()

    # -- draining ----------------------------------------------------------- #
    def _drain_cycle(self) -> None:
        with self._drain_lock:
            self._last_activity_nanos = self._clock()
            fill = self._buffer.size() / self._buffer.capacity
            if fill > _SHEDDING_THRESHOLD:
                # Under load, shed: drain and discard without storing (best-effort), but counted.
                self._shed_count += self._buffer.drain(lambda _event: None)
            else:
                event = self._buffer.poll()
                if event is not None:
                    self._process_normal(event)

    def _process_normal(self, event: TraceEvent) -> None:
        self._store.add(event)
        self._deliver(event)

    def _drain_remaining(self) -> None:
        with self._drain_lock:
            self._buffer.drain(self._process_normal)

    def on_watchdog_stale(self) -> None:
        """Invoked by the watchdog when the drain has been stale beyond the threshold."""
        if self._on_stale is None:
            return
        try:
            self._on_stale(self.stale_since_millis())
        except PROPAGATED_EXCEPTIONS:
            raise
        except BaseException:  # a hostile callback must not kill the watchdog thread
            pass

    def _deliver(self, event: TraceEvent) -> None:
        with self._subscriber_lock:
            slots = list(self._subscribers)
        for slot in slots:
            self._deliver_to_slot(slot, event)

    def _deliver_to_slot(self, slot: _SubscriberSlot, event: TraceEvent) -> None:
        if slot.busy:
            slot.dropped += 1
            return
        slot.busy = True
        try:
            result = slot.callback(event)
        except PROPAGATED_EXCEPTIONS:
            slot.busy = False
            raise
        except BaseException:  # a throwing subscriber must not stall the drain
            slot.busy = False
            return
        if isinstance(result, concurrent.futures.Future):
            result.add_done_callback(lambda _f: setattr(slot, "busy", False))
        else:
            slot.busy = False


def _atexit_close(consumer_ref: weakref.ReferenceType[BufferedEventConsumer]) -> None:
    """Flushes and stops the consumer at interpreter exit, unless it was already collected."""
    consumer = consumer_ref()
    if consumer is not None:
        consumer.close()


def _drain_loop(
    consumer_ref: weakref.ReferenceType[BufferedEventConsumer],
    wake: threading.Event,
    drain_interval_seconds: float,
) -> None:
    """Module-level so the thread's own closure holds no strong reference to its consumer.

    Resolves the weak reference once per cycle and drops it again before waiting, so an abandoned,
    un-closed consumer can be collected during the idle wait rather than staying rooted by this
    thread for the rest of the process.
    """
    while True:
        consumer = consumer_ref()
        if consumer is None or not consumer._running:
            return
        consumer._drain_cycle()
        idle = consumer._buffer.is_empty()
        del consumer
        if idle:
            wake.wait(drain_interval_seconds)
            wake.clear()


class _Watchdog:
    """Daemon timer that fires a callback when the consumer's drain is stale.

    Holds only a weak reference to its consumer (the same reason ``_drain_loop`` is module-level
    and weakref-based): an un-closed consumer must not be kept alive by its own watchdog. The run
    loop stops itself the first time the reference resolves to nothing, so the watchdog thread
    does not outlive an abandoned consumer either.
    """

    def __init__(
        self, consumer: BufferedEventConsumer, check_seconds: float = _WATCHDOG_CHECK_SECONDS
    ) -> None:
        self._consumer_ref = weakref.ref(consumer)
        self._check_seconds = check_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="narrative-trace-watchdog", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self._check_seconds):
            if not self.check():
                return

    def check(self) -> bool:
        """Fires ``on_watchdog_stale`` when the heartbeat is older than the stale threshold.

        Returns whether the consumer is still alive, so the run loop knows to stop once it isn't.
        """
        consumer = self._consumer_ref()
        if consumer is None:
            return False
        last = consumer.last_activity_nanos()
        if last != 0 and consumer._clock() - last > _WATCHDOG_STALE_NANOS:
            consumer.on_watchdog_stale()
        return True

    def stop(self) -> None:
        """Signals the run loop to stop and waits for the thread to actually exit, so a caller
        that explicitly closes its consumer can rely on no further background activity once this
        returns — the same guarantee ``close()`` already gives for the drain thread."""
        self._stop.set()
        self._thread.join(timeout=2.0)
