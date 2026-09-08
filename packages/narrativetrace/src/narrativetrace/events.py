# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Append-only events emitted during capture.

``TraceEvent``. This is the storage/transport form of tracing: context
implementations publish events as work happens, and :mod:`narrativetrace.tree` later
reconstructs immutable call trees from them.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.concurrency import ConcurrencyInfo, ThreadIdentity
from narrativetrace.ids import SpanId
from narrativetrace.outcomes import TraceOutcome
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext


class TraceEvent:
    """Base of the sealed event union. Not instantiated directly."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class EnterEvent(TraceEvent):
    """Records entry into a method, pushing a new frame.

    ``thread`` is the identity of the thread that executed the entry (canonical schema 1.2);
    ``None`` on an event built without it, which reads as "not captured", not "the main thread".
    """

    span_context: SpanContext
    timestamp_nanos: int
    signature: MethodSignature
    concurrency: ConcurrencyInfo | None = None
    thread: ThreadIdentity | None = None


@dataclass(frozen=True, slots=True)
class ExitEvent(TraceEvent):
    """Records a method exit (return or throw) with its outcome."""

    span_context: SpanContext
    timestamp_nanos: int
    outcome: TraceOutcome
    error_context: str | None = None


@dataclass(frozen=True, slots=True)
class ForkCreatedEvent(TraceEvent):
    """Lifecycle marker: a fork group was created."""

    group_id: str
    timestamp_nanos: int


@dataclass(frozen=True, slots=True)
class MergeEvent(TraceEvent):
    """Lifecycle marker: a fork group merged its collected children."""

    group_id: str
    member_count: int
    timestamp_nanos: int


@dataclass(frozen=True, slots=True)
class FireAndForgetEvent(TraceEvent):
    """Lifecycle marker: a fire-and-forget group was launched."""

    group_id: str
    timestamp_nanos: int


def span_id_of(event: TraceEvent) -> SpanId | None:
    """Returns the span id an event belongs to, or ``None`` for group lifecycle events."""
    if isinstance(event, EnterEvent | ExitEvent):
        return event.span_context.span_id
    return None
