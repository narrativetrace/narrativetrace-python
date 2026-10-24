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
    """Lifecycle marker: a fork group was created.

    ``owner_span_id`` is the span current on the launching thread when the group was created
    (B-166); ``None`` for a group created outside every span, which no request ever removes.
    """

    group_id: str
    timestamp_nanos: int
    owner_span_id: SpanId | None = None


@dataclass(frozen=True, slots=True)
class MergeEvent(TraceEvent):
    """Lifecycle marker: a fork group merged its collected children.

    ``owner_span_id`` is the span current on the merging (launching) thread (B-166); ``None``
    outside every span.
    """

    group_id: str
    member_count: int
    timestamp_nanos: int
    owner_span_id: SpanId | None = None


@dataclass(frozen=True, slots=True)
class FireAndForgetEvent(TraceEvent):
    """Lifecycle marker: a fire-and-forget group was launched.

    ``owner_span_id`` is the span current on the launching thread (B-166); ``None`` for a group
    launched outside every span.
    """

    group_id: str
    timestamp_nanos: int
    owner_span_id: SpanId | None = None


def span_id_of(event: TraceEvent) -> SpanId | None:
    """Returns the span id an event belongs to.

    Enter/exit events answer their own span; group lifecycle events answer the span that
    launched the group (``owner_span_id``), so a request's cleanup removes them with it. A group
    created outside every span has no owner: ``None``, and the event is retained (B-166).
    """
    if isinstance(event, EnterEvent | ExitEvent):
        return event.span_context.span_id
    if isinstance(event, ForkCreatedEvent | MergeEvent | FireAndForgetEvent):
        return event.owner_span_id
    return None
