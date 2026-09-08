# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Work traced under a propagated snapshot belongs to the trace that took the snapshot.

Mirrors Java ``AsyncSnapshotAdoptionTest`` case for case, twice: once over a worker thread and
once over an asyncio task. The two substrates differ in exactly the place this contract lives —
a fresh thread starts with an empty :mod:`contextvars` context, while a task starts with a *copy*
of its creator's, so it inherits the origin's stack unless a snapshot replaces it.

The synchronous log stream already narrates this work; the captured tree must not silently lose
it.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.groups import ForkJoinGroup
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

_WORKER_THREAD_NAME = "async-worker"
_JOIN_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def ctx() -> Iterator[ContextVarNarrativeContext]:
    context = ContextVarNarrativeContext()
    yield context
    context.reset()


def _sig(class_name: str, method_name: str) -> MethodSignature:
    return MethodSignature(class_name, method_name, [])


def _names(nodes: list[TraceNode]) -> list[str]:
    return [f"{n.signature.class_name}.{n.signature.method_name}" for n in nodes]


def _trace_call(ctx: ContextVarNarrativeContext, class_name: str, method_name: str) -> None:
    ctx.enter_method(_sig(class_name, method_name))
    ctx.exit_method_with_return("true")


def _run_on_thread(name: str, body: Callable[[], None]) -> None:
    """Runs ``body`` on a named thread and re-raises whatever it raised, so failures are visible."""
    failures: list[BaseException] = []

    def guarded() -> None:
        try:
            body()
        except BaseException as error:
            failures.append(error)

    thread = threading.Thread(target=guarded, name=name)
    thread.start()
    thread.join(_JOIN_TIMEOUT_SECONDS)
    assert not thread.is_alive(), "the worker thread never finished"
    if failures:
        raise failures[0]


def _run_under_snapshot_on_thread(
    ctx: ContextVarNarrativeContext, body: Callable[[], None]
) -> None:
    snapshot = ctx.snapshot()

    def worker() -> None:
        with snapshot.activate():
            body()

    _run_on_thread(_WORKER_THREAD_NAME, worker)


def _task_under_snapshot(
    ctx: ContextVarNarrativeContext, body: Callable[[], None]
) -> asyncio.Task[None]:
    """Creates (but does not await) a task running ``body`` under a snapshot taken right now."""
    snapshot = ctx.snapshot()

    async def worker() -> None:
        with snapshot.activate():
            body()

    return asyncio.create_task(worker())


class TestAdoptionOverThreads:
    def test_async_work_started_after_the_parent_returned_becomes_a_second_root(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        ctx.exit_method_with_return("OrderResult")

        _run_under_snapshot_on_thread(
            ctx, lambda: _trace_call(ctx, "NotificationService", "notifyOrderPlaced")
        )

        assert _names(ctx.capture_trace().roots) == [
            "OrderService.placeOrder",
            "NotificationService.notifyOrderPlaced",
        ]

    def test_async_work_started_inside_the_parent_becomes_a_child(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        _run_under_snapshot_on_thread(
            ctx, lambda: _trace_call(ctx, "NotificationService", "notifyOrderPlaced")
        )
        ctx.exit_method_with_return("OrderResult")

        roots = ctx.capture_trace().roots

        assert _names(roots) == ["OrderService.placeOrder"]
        assert _names(roots[0].children) == ["NotificationService.notifyOrderPlaced"]

    def test_the_adopted_node_reports_the_thread_that_ran_it(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        ctx.exit_method_with_return("OrderResult")

        _run_under_snapshot_on_thread(
            ctx, lambda: _trace_call(ctx, "NotificationService", "notifyOrderPlaced")
        )

        adopted = ctx.capture_trace().roots[1]
        assert adopted.thread is not None
        assert adopted.thread.name == _WORKER_THREAD_NAME

    def test_nested_async_calls_keep_their_own_shape(self, ctx: ContextVarNarrativeContext) -> None:
        def nested() -> None:
            ctx.enter_method(_sig("NotificationService", "notifyOrderPlaced"))
            ctx.enter_method(_sig("EmailGateway", "send"))
            ctx.exit_method_with_return("true")
            ctx.exit_method_with_return("true")

        ctx.enter_method(_sig("OrderService", "placeOrder"))
        _run_under_snapshot_on_thread(ctx, nested)
        ctx.exit_method_with_return("OrderResult")

        root = ctx.capture_trace().roots[0]
        assert _names(root.children) == ["NotificationService.notifyOrderPlaced"]
        assert _names(root.children[0].children) == ["EmailGateway.send"]

    def test_work_on_a_thread_that_never_activated_the_snapshot_stays_out(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        ctx.exit_method_with_return("OrderResult")

        _run_on_thread("unrelated", lambda: _trace_call(ctx, "Unrelated", "backgroundSweep"))

        assert _names(ctx.capture_trace().roots) == ["OrderService.placeOrder"]

    def test_fork_group_children_are_not_counted_twice(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        group = ForkJoinGroup.create(ctx)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(group.wrap(lambda: _trace_call(ctx, "InventoryService", "reserve"))).result(
                _JOIN_TIMEOUT_SECONDS
            )
        group.merge()
        ctx.exit_method_with_return("OrderResult")

        root = ctx.capture_trace().roots[0]
        assert _names(root.children) == ["InventoryService.reserve"]

    def test_adoption_dies_with_the_snapshotting_stack(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        ctx.exit_method_with_return("OrderResult")
        snapshot = ctx.snapshot()
        ctx.reset()

        def worker() -> None:
            with snapshot.activate():
                _trace_call(ctx, "NotificationService", "notifyOrderPlaced")

        _run_on_thread(_WORKER_THREAD_NAME, worker)

        assert ctx.capture_trace().roots == []

    def test_many_async_children_all_land_in_the_tree(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        for index in range(50):
            name = f"notify{index}"
            _run_under_snapshot_on_thread(
                ctx,
                lambda name=name: _trace_call(ctx, "NotificationService", name),  # type: ignore[misc]
            )
        ctx.exit_method_with_return("OrderResult")

        assert len(ctx.capture_trace().roots[0].children) == 50


class TestAdoptionOverAsyncioTasks:
    def test_async_work_started_after_the_parent_returned_becomes_a_second_root(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        async def scenario() -> TraceTree:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            ctx.exit_method_with_return("OrderResult")
            await _task_under_snapshot(
                ctx, lambda: _trace_call(ctx, "NotificationService", "notifyOrderPlaced")
            )
            return ctx.capture_trace()

        assert _names(asyncio.run(scenario()).roots) == [
            "OrderService.placeOrder",
            "NotificationService.notifyOrderPlaced",
        ]

    def test_a_task_created_inside_the_parent_and_awaited_later_becomes_a_child(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """Placement follows submit time: the parent had returned before the task even ran."""

        async def scenario() -> TraceTree:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            task = _task_under_snapshot(
                ctx, lambda: _trace_call(ctx, "NotificationService", "notifyOrderPlaced")
            )
            ctx.exit_method_with_return("OrderResult")
            await task
            return ctx.capture_trace()

        roots = asyncio.run(scenario()).roots

        assert _names(roots) == ["OrderService.placeOrder"]
        assert _names(roots[0].children) == ["NotificationService.notifyOrderPlaced"]

    def test_the_adopted_node_reports_the_thread_that_ran_it(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        async def scenario() -> TraceTree:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            ctx.exit_method_with_return("OrderResult")
            await _task_under_snapshot(
                ctx, lambda: _trace_call(ctx, "NotificationService", "notifyOrderPlaced")
            )
            return ctx.capture_trace()

        adopted = asyncio.run(scenario()).roots[1]

        assert adopted.thread is not None
        assert adopted.thread.name == threading.current_thread().name

    def test_nested_async_calls_keep_their_own_shape(self, ctx: ContextVarNarrativeContext) -> None:
        def nested() -> None:
            ctx.enter_method(_sig("NotificationService", "notifyOrderPlaced"))
            ctx.enter_method(_sig("EmailGateway", "send"))
            ctx.exit_method_with_return("true")
            ctx.exit_method_with_return("true")

        async def scenario() -> TraceTree:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            await _task_under_snapshot(ctx, nested)
            ctx.exit_method_with_return("OrderResult")
            return ctx.capture_trace()

        root = asyncio.run(scenario()).roots[0]
        assert _names(root.children) == ["NotificationService.notifyOrderPlaced"]
        assert _names(root.children[0].children) == ["EmailGateway.send"]

    def test_work_in_a_task_that_never_activated_the_snapshot_inherits_the_callers_stack(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """Where this runtime's shape diverges from Java's: a task copies its creator's context.

        A thread that never activated a snapshot is invisible (it starts with an empty context and
        gets its own stack); a task started from inside a traced call inherits the caller's stack
        itself, so its work is the caller's work — no adoption involved.
        """

        async def scenario() -> TraceTree:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            await asyncio.create_task(_traced_in_task(ctx, "Unrelated", "backgroundSweep"))
            ctx.exit_method_with_return("OrderResult")
            return ctx.capture_trace()

        roots = asyncio.run(scenario()).roots

        assert _names(roots) == ["OrderService.placeOrder"]
        assert _names(roots[0].children) == ["Unrelated.backgroundSweep"]

    def test_fork_group_children_are_not_counted_twice(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        async def scenario() -> TraceTree:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            group = ForkJoinGroup.create(ctx)
            await asyncio.gather(
                group.run_async(lambda: _traced_in_task(ctx, "InventoryService", "reserve"))
            )
            group.merge()
            ctx.exit_method_with_return("OrderResult")
            return ctx.capture_trace()

        root = asyncio.run(scenario()).roots[0]
        assert _names(root.children) == ["InventoryService.reserve"]

    def test_adoption_dies_with_the_snapshotting_stack(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        async def scenario() -> TraceTree:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            ctx.exit_method_with_return("OrderResult")
            snapshot = ctx.snapshot()
            ctx.reset()

            async def worker() -> None:
                with snapshot.activate():
                    _trace_call(ctx, "NotificationService", "notifyOrderPlaced")

            await asyncio.create_task(worker())
            return ctx.capture_trace()

        assert asyncio.run(scenario()).roots == []

    def test_many_async_children_all_land_in_the_tree(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        async def scenario() -> TraceTree:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            tasks = [
                _task_under_snapshot(
                    ctx,
                    lambda name=f"notify{index}": _trace_call(  # type: ignore[misc]
                        ctx, "NotificationService", name
                    ),
                )
                for index in range(50)
            ]
            await asyncio.gather(*tasks)
            ctx.exit_method_with_return("OrderResult")
            return ctx.capture_trace()

        assert len(asyncio.run(scenario()).roots[0].children) == 50


async def _traced_in_task(
    ctx: ContextVarNarrativeContext, class_name: str, method_name: str
) -> None:
    ctx.enter_method(_sig(class_name, method_name))
    await asyncio.sleep(0)
    ctx.exit_method_with_return("true")
