# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The retention class: adopted, late, and forked/fire-and-forget worker state must not outlive
the request it belongs to.

Mirrors Java ``AsyncLifecycleContractTest`` (a bug-hunt supplement finding). Each probe checks
the underlying store directly
(``ctx._store.events()`` / ``ctx._span_contexts``), not just ``capture_trace()``'s output — the
bug in every one of these findings was retained-but-invisible state: the *output* tree already
looked right, while raw events accumulated in the shared store forever, uncounted.
"""

from __future__ import annotations

import threading

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.events import EnterEvent
from narrativetrace.groups import FireAndForgetGroup, ForkJoinGroup
from narrativetrace.loss import TraceLoss
from narrativetrace.signature import MethodSignature

_JOIN_TIMEOUT_SECONDS = 5.0


def _sig(class_name: str, method_name: str) -> MethodSignature:
    return MethodSignature(class_name, method_name, [])


def _trace_call(ctx: ContextVarNarrativeContext, class_name: str, method_name: str) -> None:
    ctx.enter_method(_sig(class_name, method_name))
    ctx.exit_method_with_return("true")


class TestAdoptedSpansDoNotSurviveReset:
    """A bug-hunt finding: reset() must clear spans already adopted from finished workers, not
    only its own — an adopted worker subtree is this request's own reportable trace.
    """

    def test_adopted_worker_spans_and_events_do_not_survive_the_parent_reset(self) -> None:
        ctx = ContextVarNarrativeContext()
        _trace_call(ctx, "OrderService", "placeOrder")
        snapshot = ctx.snapshot()

        def worker() -> None:
            with snapshot.activate():
                _trace_call(ctx, "NotificationService", "notifyOrderPlaced")

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(_JOIN_TIMEOUT_SECONDS)
        assert not thread.is_alive()

        assert len(ctx._store.events()) == 4  # sanity: the adopted work really landed first
        assert len(ctx._span_contexts) == 2

        ctx.reset()

        assert ctx._store.events() == []
        assert ctx._span_contexts == {}


class TestLateCompletionAfterReset:
    """A bug-hunt finding: a worker that finishes *after* its parent has already reset must not
    retain its spans — discarded, and counted as loss, not silently kept in the shared store
    forever.
    """

    def test_a_worker_that_finishes_after_the_parent_reset_is_discarded_and_counted(self) -> None:
        ctx = ContextVarNarrativeContext()
        _trace_call(ctx, "OrderService", "placeOrder")
        snapshot = ctx.snapshot()
        proceed = threading.Event()

        def worker() -> None:
            proceed.wait(_JOIN_TIMEOUT_SECONDS)
            with snapshot.activate():
                _trace_call(ctx, "NotificationService", "notifyOrderPlaced")

        thread = threading.Thread(target=worker)
        thread.start()

        before = ctx.trace_loss()
        ctx.reset()
        assert len(ctx._retained) == 1  # the reset stack is held alive for the pending snapshot
        proceed.set()
        thread.join(_JOIN_TIMEOUT_SECONDS)
        assert not thread.is_alive()

        assert ctx._store.events() == []
        assert ctx._span_contexts == {}
        assert ctx.trace_loss().since(before) == TraceLoss(0, 0, 0, discarded_spans=1)
        assert ctx._retained == set()  # released once the late snapshot resolved

    def test_two_late_workers_both_count_toward_the_same_discarded_total(self) -> None:
        """Guards the accumulator itself: a second discard must add to the first, not replace
        it — otherwise a busy request under-reports how much of its background tail it lost. Two
        separate snapshots (this API's supported one-snapshot-per-activation shape, matching how
        ForkJoinGroup/FireAndForgetGroup use it for each concurrent task), not one shared between
        threads.
        """
        ctx = ContextVarNarrativeContext()
        _trace_call(ctx, "OrderService", "placeOrder")
        proceed = threading.Event()

        def worker(snapshot: object, method_name: str) -> None:
            proceed.wait(_JOIN_TIMEOUT_SECONDS)
            with snapshot.activate():  # type: ignore[attr-defined]
                _trace_call(ctx, "NotificationService", method_name)

        # Both snapshots taken from the main thread's origin stack before any worker starts —
        # ctx.snapshot() reads contextvars.ContextVar.get() for the CALLING thread, so taking it
        # from inside a fresh worker thread would snapshot that thread's own empty stack instead.
        threads = [
            threading.Thread(target=worker, args=(ctx.snapshot(), name))
            for name in ("notifyOrderPlaced", "notifyOrderShipped")
        ]
        for thread in threads:
            thread.start()

        before = ctx.trace_loss()
        ctx.reset()
        proceed.set()
        for thread in threads:
            thread.join(_JOIN_TIMEOUT_SECONDS)
            assert not thread.is_alive()

        assert ctx.trace_loss().since(before) == TraceLoss(0, 0, 0, discarded_spans=2)
        assert ctx._retained == set()

    def test_a_worker_that_finishes_before_the_parent_reset_is_not_counted_as_discarded(
        self,
    ) -> None:
        """No false positives: the ordinary, on-time case must not report a phantom discard."""
        ctx = ContextVarNarrativeContext()
        _trace_call(ctx, "OrderService", "placeOrder")
        snapshot = ctx.snapshot()

        def worker() -> None:
            with snapshot.activate():
                _trace_call(ctx, "NotificationService", "notifyOrderPlaced")

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(_JOIN_TIMEOUT_SECONDS)

        before = ctx.trace_loss()
        ctx.reset()

        assert ctx.trace_loss().since(before) == TraceLoss.none()


class TestPurgeIsIdempotent:
    """``_purge_stack`` (the shared machinery behind ``reset()`` and ``clear_local_trace()``)
    must tolerate a span id that is already gone from ``_span_contexts`` — ``close_and_collect()``
    returns a snapshot of ``known``/``adopted`` without clearing them, so purging the same stack
    a second time (e.g. a discarded late worker whose spans a still-open parent already purged
    once) must not raise ``KeyError``.
    """

    def test_purging_the_same_stack_twice_does_not_raise(self) -> None:
        ctx = ContextVarNarrativeContext()
        _trace_call(ctx, "OrderService", "placeOrder")
        stack = ctx._get_stack()

        ctx._purge_stack(stack)
        assert ctx._span_contexts == {}

        ctx._purge_stack(stack)  # same span ids again — must not raise
        assert ctx._span_contexts == {}


class TestForkAndFireAndForgetPurgeRawEvents:
    """A bug-hunt finding: once a fork/fire-and-forget helper has collected a worker's roots as
    copied TraceNodes, the worker's raw events must be gone from the shared store — otherwise
    every unit
    of concurrent work leaks its raw events for the rest of the process, invisible to every
    capture but never freed.
    """

    def test_forked_worker_spans_are_gone_once_their_roots_have_been_collected(self) -> None:
        ctx = ContextVarNarrativeContext()
        _trace_call(ctx, "OrderService", "placeOrder")
        group = ForkJoinGroup.create(ctx)

        def task() -> None:
            _trace_call(ctx, "Worker", "doWork")

        group.wrap(task)()  # _collect() runs in its finally, before merge() ever sees it

        raw_worker_spans = [e for e in ctx._store.events() if _is_call(e, "Worker", "doWork")]
        assert raw_worker_spans == []

        merged = group.merge()
        assert [n.signature.method_name for n in merged] == ["doWork"]  # still in the output

    def test_fire_and_forget_worker_spans_are_gone_once_their_roots_have_been_collected(
        self,
    ) -> None:
        ctx = ContextVarNarrativeContext()
        _trace_call(ctx, "OrderService", "placeOrder")
        group = FireAndForgetGroup.create(ctx, "OrderService")

        def task() -> None:
            _trace_call(ctx, "Worker", "doWork")

        group.wrap(task)()

        raw_worker_spans = [e for e in ctx._store.events() if _is_call(e, "Worker", "doWork")]
        assert raw_worker_spans == []

        roots = group.child_roots()  # already collected before wrap() returned; still available
        assert [n.signature.method_name for n in roots] == ["doWork"]


def _is_call(event: object, class_name: str, method_name: str) -> bool:
    return (
        isinstance(event, EnterEvent)
        and event.signature.class_name == class_name
        and event.signature.method_name == method_name
    )
