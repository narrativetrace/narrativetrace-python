# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for EventStoreSubscriber await ergonomics."""

from __future__ import annotations

import asyncio

from narrativetrace.events import EnterEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.pipeline.subscriber import EventStoreSubscriber
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

TRACE = TraceId("a" * 32)


def _event(hex_char: str) -> EnterEvent:
    ctx = SpanContext(trace_id=TRACE, span_id=SpanId(hex_char * 16))
    return EnterEvent(ctx, 0, MethodSignature("Svc", "m", []))


def test_stores_events() -> None:
    sub = EventStoreSubscriber()
    sub.on_event(_event("a"))
    assert len(sub.events()) == 1


def test_await_events_resolves_when_target_reached() -> None:
    sub = EventStoreSubscriber()
    fut = sub.await_events(2)
    assert not fut.done()
    sub.on_event(_event("a"))
    assert not fut.done()
    sub.on_event(_event("b"))
    assert fut.result(timeout=1) is None


def test_await_events_already_met_resolves_immediately() -> None:
    sub = EventStoreSubscriber()
    sub.on_event(_event("a"))
    sub.on_event(_event("b"))
    fut = sub.await_events(2)
    assert fut.done()


def test_await_complete_resolves_on_complete() -> None:
    sub = EventStoreSubscriber()
    fut = sub.await_complete()
    assert not fut.done()
    sub.on_complete()
    assert fut.result(timeout=1) is None


def test_on_complete_is_idempotent() -> None:
    sub = EventStoreSubscriber()
    sub.on_complete()
    sub.on_complete()  # must not raise
    assert sub.await_complete().done()


def test_await_events_is_asyncio_friendly() -> None:
    sub = EventStoreSubscriber()

    async def main() -> None:
        fut = asyncio.wrap_future(sub.await_events(1))
        sub.on_event(_event("a"))
        await asyncio.wait_for(fut, timeout=1)

    asyncio.run(main())
