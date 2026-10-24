# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-166: group lifecycle events belong to the span that launched the group."""

from __future__ import annotations

import threading

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.events import (
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
    span_id_of,
)
from narrativetrace.groups import FireAndForgetGroup, ForkJoinGroup
from narrativetrace.pipeline.event_store import EventStore
from narrativetrace.signature import MethodSignature

_GROUP_EVENTS = (ForkCreatedEvent, MergeEvent, FireAndForgetEvent)


def _sig(cls: str = "Service", method: str = "request") -> MethodSignature:
    return MethodSignature(cls, method, [])


def _context() -> tuple[ContextVarNarrativeContext, EventStore]:
    store = EventStore()
    return ContextVarNarrativeContext(store=store), store


def test_group_events_carry_the_launching_span_as_owner() -> None:
    context, store = _context()
    parent = context.enter_method(_sig())
    group = ForkJoinGroup.create(context)
    group.wrap(lambda: None)()
    group.merge()
    FireAndForgetGroup.create(context, "Service")
    context.exit_method_with_return("done", span_id=parent)

    group_events = [e for e in store.events() if isinstance(e, _GROUP_EVENTS)]
    assert len(group_events) == 3
    assert [span_id_of(e) for e in group_events] == [parent] * 3
    context.reset()


def test_completed_fire_and_forget_requests_leave_no_lifecycle_events() -> None:
    context, store = _context()
    for _ in range(20):
        parent = context.enter_method(_sig())
        FireAndForgetGroup.create(context, "Service")
        context.exit_method_with_return("done", span_id=parent)
        context.reset()

    assert [e for e in store.events() if isinstance(e, FireAndForgetEvent)] == []


def test_a_capture_sees_its_own_group_events_and_no_other_requests() -> None:
    context, store = _context()

    def other_request() -> None:
        span = context.enter_method(_sig("Other", "req"))
        ForkJoinGroup.create(context).merge()
        context.exit_method_with_return("1", span_id=span)

    other = threading.Thread(target=other_request)
    other.start()
    other.join()
    parent = context.enter_method(_sig())
    ForkJoinGroup.create(context).merge()
    context.exit_method_with_return("1", span_id=parent)

    reportable = {parent}
    mine = [
        span_id_of(e)
        for e in store.events()
        if isinstance(e, ForkCreatedEvent) and span_id_of(e) in reportable
    ]
    assert mine == [parent]
    assert len([e for e in store.events() if isinstance(e, ForkCreatedEvent)]) == 2
    context.reset()
