# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for ForkJoinGroup and FireAndForgetGroup over asyncio and threads."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager

import pytest

from narrativetrace.concurrency import ConcurrencyKind
from narrativetrace.context import ContextSnapshot, ContextVarNarrativeContext
from narrativetrace.groups import FireAndForgetGroup, ForkJoinGroup
from narrativetrace.metadata import EnduserId, HttpRoute, SessionId, TenantId
from narrativetrace.outcomes import Incomplete
from narrativetrace.signature import MethodSignature
from narrativetrace.trace_object import trace_object


class Worker:
    def do(self, label: str) -> str:
        return f"did {label}"

    async def do_async(self, label: str) -> str:
        await asyncio.sleep(0)
        return f"did {label}"

    async def cancellable(self) -> str:
        await asyncio.sleep(10)
        return "never"


@pytest.fixture
def ctx() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext()


def _all_concurrency(nodes: list) -> list:  # type: ignore[type-arg]
    out = []
    for node in nodes:
        if node.concurrency is not None:
            out.append(node.concurrency)
        out += _all_concurrency(node.children)
    return out


class TestForkJoinAsyncio:
    def test_merged_children_carry_shared_group_id(self, ctx: ContextVarNarrativeContext) -> None:
        async def main() -> object:
            root = ctx.enter_method(_sig())
            worker = trace_object(Worker(), ctx)
            group = ForkJoinGroup.create(ctx)
            await asyncio.gather(
                group.run_async(lambda: worker.do_async("a")),
                group.run_async(lambda: worker.do_async("b")),
            )
            group.merge()
            ctx.exit_method_with_return(None, span_id=root)
            return ctx.capture_trace()

        tree = asyncio.run(main())
        infos = _all_concurrency(tree.roots)  # type: ignore[attr-defined]
        assert len(infos) == 2
        assert {i.group_id for i in infos} == {"fork-1"} or len({i.group_id for i in infos}) == 1
        assert all(i.kind is ConcurrencyKind.FORK_JOIN for i in infos)
        assert all(i.task_label == "Worker.do_async" for i in infos)


class TestForkJoinThreads:
    def test_over_thread_pool_executor(self, ctx: ContextVarNarrativeContext) -> None:
        root = ctx.enter_method(_sig())
        worker = trace_object(Worker(), ctx)
        group = ForkJoinGroup.create(ctx)

        def make_task(label: str) -> Callable[[], str]:
            return group.wrap(lambda: worker.do(label))

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(make_task(str(i))) for i in range(3)]
            for future in futures:
                future.result()
        group.merge()
        ctx.exit_method_with_return(None, span_id=root)
        infos = _all_concurrency(ctx.capture_trace().roots)
        assert len(infos) == 3
        assert all(i.kind is ConcurrencyKind.FORK_JOIN for i in infos)


class TestFullIdentityPropagation:
    def test_children_inherit_request_and_user_metadata(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.set_request_context("POST", HttpRoute.of("/orders"), None)
        ctx.set_user_context(EnduserId.of("u1"), SessionId.of("s1"), TenantId.of("t1"))
        root = ctx.enter_method(_sig())
        worker = trace_object(Worker(), ctx)
        group = ForkJoinGroup.create(ctx)

        async def main() -> None:
            await group.run_async(lambda: worker.do_async("x"))
            group.merge()

        asyncio.run(main())
        ctx.exit_method_with_return(None, span_id=root)
        # find the merged child span and assert it carries the parent's tenant/user identity
        merged = ctx.capture_trace().roots[0].children[0]
        span = merged.span_context
        assert span is not None
        assert str(span.tenant_id) == "t1"
        assert str(span.enduser_id) == "u1"
        assert span.http_route is not None and str(span.http_route) == "/orders"


class TestFireAndForget:
    def test_launcher_marker_grafted_at_create(self, ctx: ContextVarNarrativeContext) -> None:
        root = ctx.enter_method(_sig())
        FireAndForgetGroup.create(ctx, "Launcher")
        ctx.exit_method_with_return(None, span_id=root)
        child = ctx.capture_trace().roots[0].children[0]
        assert child.signature.method_name == "fire-and-forget"
        assert child.concurrency is not None
        assert child.concurrency.kind is ConcurrencyKind.FIRE_AND_FORGET

    def test_child_roots_collected_and_tagged(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig())
        worker = trace_object(Worker(), ctx)
        group = FireAndForgetGroup.create(ctx, "Launcher")
        group.wrap(lambda: worker.do("bg"))()
        roots = group.child_roots()
        assert len(roots) == 1
        assert roots[0].concurrency is not None
        assert roots[0].concurrency.kind is ConcurrencyKind.FIRE_AND_FORGET


class TestAdoptionOptOut:
    """Both helpers re-emit their own children, so neither may hand them over as well.

    Pinned at the activation seam rather than by counting nodes: until snapshot adoption
    exists the two activations behave identically, and the day it exists a helper on the
    adopting path shows every child twice.
    """

    def test_fork_join_wrap_activates_without_adoption(self) -> None:
        recorder = _RecordingContext()
        ForkJoinGroup.create(recorder).wrap(lambda: None)()
        assert recorder.activations == ["activate_without_adoption"]

    def test_fork_join_run_async_activates_without_adoption(self) -> None:
        recorder = _RecordingContext()

        async def main() -> None:
            await ForkJoinGroup.create(recorder).run_async(_nothing)

        asyncio.run(main())
        assert recorder.activations == ["activate_without_adoption"]

    def test_fire_and_forget_wrap_activates_without_adoption(self) -> None:
        recorder = _RecordingContext()
        FireAndForgetGroup.create(recorder, "Launcher").wrap(lambda: None)()
        assert recorder.activations == ["activate_without_adoption"]

    def test_fire_and_forget_run_async_activates_without_adoption(self) -> None:
        recorder = _RecordingContext()

        async def main() -> None:
            await FireAndForgetGroup.create(recorder, "Launcher").run_async(_nothing)

        asyncio.run(main())
        assert recorder.activations == ["activate_without_adoption"]


class TestCancellation:
    def test_cancelled_member_is_incomplete(self, ctx: ContextVarNarrativeContext) -> None:
        async def main() -> object:
            worker = trace_object(Worker(), ctx)
            group = ForkJoinGroup.create(ctx)

            async def member() -> None:
                await group.run_async(worker.cancellable)

            task = asyncio.ensure_future(member())
            await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            group.merge()
            return ctx.capture_trace()

        tree = asyncio.run(main())
        merged = tree.roots  # type: ignore[attr-defined]
        assert any(isinstance(n.outcome, Incomplete) for n in merged)


def _sig() -> MethodSignature:
    return MethodSignature("Root", "handle", [])


async def _nothing() -> None:
    """A member that traces nothing: the activation, not the work, is under test."""


class _RecordingSnapshot(ContextSnapshot):
    """Delegating snapshot that records which of the two activations a caller chose."""

    def __init__(self, delegate: ContextSnapshot, activations: list[str]) -> None:
        self._delegate = delegate
        self._activations = activations

    def activate(self) -> AbstractContextManager[None]:
        self._activations.append("activate")
        return self._delegate.activate()

    def activate_without_adoption(self) -> AbstractContextManager[None]:
        self._activations.append("activate_without_adoption")
        return self._delegate.activate_without_adoption()


class _RecordingContext(ContextVarNarrativeContext):
    """A real context whose snapshots are wrapped in :class:`_RecordingSnapshot`."""

    def __init__(self) -> None:
        super().__init__()
        self.activations: list[str] = []

    def snapshot(self) -> ContextSnapshot:
        return _RecordingSnapshot(super().snapshot(), self.activations)


class TestForkFromAsyncParent:
    """A group created INSIDE an async traced method parents to that method.

    Async spans register through ``begin_scope`` (the scoped parent), not the
    active stack, so a parent taken from ``peek_active`` alone is ``None``
    there and merged children silently land as roots — the core defect the
    2026-08-27 demo tour surfaced. ``current_span_id`` now resolves the way
    span creation does: scoped parent first, then the active stack, then a
    propagated snapshot's parent.
    """

    def test_children_forked_from_an_async_method_land_under_it_not_as_roots(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        worker = trace_object(Worker(), ctx)

        class Coordinator:
            async def coordinate(self) -> str:
                group = ForkJoinGroup.create(ctx)
                await asyncio.gather(
                    group.run_async(lambda: worker.do_async("a")),
                    group.run_async(lambda: worker.do_async("b")),
                )
                group.merge()
                return "coordinated"

        coordinator = trace_object(Coordinator(), ctx)

        async def main() -> object:
            await coordinator.coordinate()
            return ctx.capture_trace()

        tree = asyncio.run(main())
        roots = tree.roots  # type: ignore[attr-defined]
        assert len(roots) == 1, [getattr(r, "signature", r) for r in roots]
        infos = _all_concurrency(roots)
        assert len(infos) == 2
        assert all(i.kind is ConcurrencyKind.FORK_JOIN for i in infos)
