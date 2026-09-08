# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Event-storing subscriber with await utilities and completion signalling.

``EventStoreSubscriber``. Useful in tests or stream-driven integrations that need
deterministic waiting. ``await_events`` / ``await_complete`` return
:class:`concurrent.futures.Future` objects, which are asyncio-friendly (wrap with
:func:`asyncio.wrap_future`) and also support a blocking ``.result(timeout=...)``.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future

from narrativetrace.events import TraceEvent
from narrativetrace.pipeline.event_store import EventStore


class EventStoreSubscriber:
    """Stores incoming events and exposes count/completion await utilities."""

    def __init__(self) -> None:
        self._store = EventStore()
        self._lock = threading.Lock()
        self._count = 0
        self._awaiters: list[tuple[int, Future[None]]] = []
        self._complete: Future[None] = Future()

    def on_event(self, event: TraceEvent) -> None:
        """Records an event and resolves any awaiters whose target count is now met."""
        self._store.add(event)
        with self._lock:
            self._count += 1
            count = self._count
            ready = [future for target, future in self._awaiters if count >= target]
            self._awaiters = [(t, f) for t, f in self._awaiters if count < t]
        for future in ready:
            if not future.done():
                future.set_result(None)

    def on_complete(self) -> None:
        """Signals upstream completion, resolving :meth:`await_complete`."""
        if not self._complete.done():
            self._complete.set_result(None)

    def events(self) -> list[TraceEvent]:
        return self._store.events()

    def await_complete(self) -> Future[None]:
        """Returns a future that resolves when :meth:`on_complete` is called."""
        return self._complete

    def await_events(self, count: int) -> Future[None]:
        """Returns a future resolving once at least ``count`` events have been observed."""
        future: Future[None] = Future()
        with self._lock:
            if self._count >= count:
                future.set_result(None)
            else:
                self._awaiters.append((count, future))
        return future
