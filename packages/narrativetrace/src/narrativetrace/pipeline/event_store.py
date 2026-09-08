# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Thread-safe in-memory store of drained trace events.

``EventStore``. All access is serialised on an instance lock: a buffered consumer's
drain thread calls :meth:`add` while request threads call :meth:`events`, :meth:`clear`, and
:meth:`remove_spans`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from narrativetrace.events import TraceEvent, span_id_of
from narrativetrace.ids import SpanId


class EventStore:
    """Append-only, lock-guarded store of trace events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[TraceEvent] = []

    def add(self, event: TraceEvent) -> None:
        """Appends an event to the store."""
        with self._lock:
            self._events.append(event)

    def events(self) -> list[TraceEvent]:
        """Returns a snapshot copy of all stored events."""
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        """Removes all stored events."""
        with self._lock:
            self._events.clear()

    def remove_spans(self, span_ids: Iterable[SpanId]) -> None:
        """Removes only enter/exit events for ``span_ids`` (request-scoped cleanup)."""
        ids = set(span_ids)
        if not ids:
            return
        with self._lock:
            self._events = [e for e in self._events if span_id_of(e) not in ids]
