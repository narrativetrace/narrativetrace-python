# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Fan-out pipeline with one synchronous path and one optional best-effort path.

``DualPathPipeline`` / ``EventPipeline``. :meth:`publish` isolates each path — a
throwing listener or consumer is swallowed, never propagates into application code, and never
prevents the other path from receiving the event. This guarantee is load-bearing for deferred
async exits (core-pipeline §TS-PIPE-1).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from narrativetrace._boundary import PROPAGATED_EXCEPTIONS
from narrativetrace.events import TraceEvent
from narrativetrace.ids import SpanId


class _BestEffortConsumer(Protocol):
    def accept(self, event: TraceEvent) -> None: ...


class DualPathPipeline:
    """Routes each event to an inline sync listener and an optional best-effort consumer."""

    def __init__(
        self,
        synchronous_listener: Callable[[TraceEvent], None] | None = None,
        best_effort_consumer: _BestEffortConsumer | None = None,
    ) -> None:
        self._sync = synchronous_listener
        self._best_effort = best_effort_consumer

    def publish(self, event: TraceEvent) -> None:
        """Delivers to both paths; a failure in either is swallowed and never reaches the app."""
        if self._sync is not None:
            try:
                self._sync(event)
            except PROPAGATED_EXCEPTIONS:
                raise
            except BaseException:  # observability failure must never become an application failure
                pass
        if self._best_effort is not None:
            try:
                self._best_effort.accept(event)
            except PROPAGATED_EXCEPTIONS:
                raise
            except BaseException:  # observability failure must never become an application failure
                pass

    def has_store(self) -> bool:
        """Whether the best-effort path exposes stored events for later retrieval."""
        return hasattr(self._best_effort, "events")

    def flush(self) -> None:
        """Drains buffered events so they become visible via :meth:`events`."""
        flush = getattr(self._best_effort, "flush", None)
        if flush is not None:
            flush()

    def events(self) -> list[TraceEvent]:
        """Returns the events currently visible from the best-effort path."""
        events = getattr(self._best_effort, "events", None)
        return events() if events is not None else []

    def clear(self) -> None:
        """Clears retained events and derived state on the best-effort path."""
        clear = getattr(self._best_effort, "clear", None)
        if clear is not None:
            clear()

    def clear_spans(self, span_ids: Iterable[SpanId]) -> None:
        """Removes only the stored events belonging to ``span_ids`` (request-scoped cleanup)."""
        remove = getattr(self._best_effort, "remove_spans", None)
        if remove is not None:
            remove(span_ids)

    def close(self) -> None:
        """Closes the best-effort consumer if it is closeable; failures are swallowed."""
        close = getattr(self._best_effort, "close", None)
        if close is None:
            return
        try:
            close()
        except PROPAGATED_EXCEPTIONS:
            raise
        except BaseException:  # best-effort — close failure is not fatal
            pass
