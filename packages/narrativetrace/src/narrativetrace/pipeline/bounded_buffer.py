# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Bounded ring buffer for trace events (overwrites oldest on overflow).

``BoundedEventBuffer``. Java uses a lock-free MPSC ring with cache-line padding backed
by an eagerly-allocated ``Slot[]`` sized to capacity; on CPython the GIL makes the lock-free part
moot, so this is a lock-guarded :class:`collections.deque` with a ``maxlen`` — appending past
capacity discards the oldest event, matching Java's "under backpressure you see the most recent
activity, not stale history" contract.

The cross-runtime buffered-consumer defaults contract (owner, 2026-08-31) fixes the buffer at
``capacity`` and never grows it; that is the only public commitment. How the underlying memory is
allocated over time is an implementation detail, not a feature: ``deque(maxlen=...)`` happens to
grow its backing linked blocks incrementally as items are appended rather than pre-allocating
``capacity`` slots up front (unlike Java's array-backed ring buffer), so a `BoundedEventBuffer`
sized to the 65,536-event default costs nothing until events actually arrive — but nothing here
exposes that timing as a knob, and there is no ``initial_capacity`` parameter anywhere in the
pipeline.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable

from narrativetrace.events import TraceEvent


class BoundedEventBuffer:
    """A capacity-bounded, overwrite-oldest event buffer (multi-producer, single-consumer)."""

    def __init__(self, capacity: int) -> None:
        self._capacity = max(1, capacity)
        self._lock = threading.Lock()
        self._buffer: deque[TraceEvent] = deque(maxlen=self._capacity)
        self._overwritten = 0

    def put(self, event: TraceEvent) -> None:
        """Enqueues an event; overwrites the oldest when full. Always succeeds.

        An overwrite is counted (a bug-hunt finding: Java's ``BoundedEventBuffer`` advanced past
        a full ring without counting what it skipped, so ``TraceLoss`` silently underreported —
        ``deque(maxlen=...)``'s automatic oldest-eviction has the identical blind spot unless the
        eviction is detected and counted here, before it happens).
        """
        with self._lock:
            if len(self._buffer) >= self._capacity:
                self._overwritten += 1
            self._buffer.append(event)

    def poll(self) -> TraceEvent | None:
        """Dequeues the oldest event, or ``None`` when empty."""
        with self._lock:
            return self._buffer.popleft() if self._buffer else None

    def drain(self, action: Callable[[TraceEvent], None]) -> int:
        """Drains all currently available events to ``action`` (invoked outside the lock).

        Returns how many events were drained, so a caller discarding them (shedding) can count
        the loss rather than letting it vanish uncounted.
        """
        with self._lock:
            drained = list(self._buffer)
            self._buffer.clear()
        for event in drained:
            action(event)
        return len(drained)

    def overwritten_count(self) -> int:
        """How many events this buffer has discarded by overwriting them while full."""
        with self._lock:
            return self._overwritten

    def size(self) -> int:
        """Approximate number of unconsumed events (0..capacity)."""
        with self._lock:
            return len(self._buffer)

    @property
    def capacity(self) -> int:
        """The buffer capacity."""
        return self._capacity

    def is_empty(self) -> bool:
        """Whether the buffer currently holds no events."""
        with self._lock:
            return not self._buffer
