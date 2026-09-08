# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Concurrency stress suite for the adoption/live-child/reset seams — the context-side counterpart
to test_pipeline_stress.py's ring/consumer/store suite. See documentation/concurrency-stress.md for
the invariant table.

Every scenario that can actually interleave under asyncio (anything spanning an ``await``) runs
under both real OS threads and asyncio tasks: asyncio task interleaving was untested for this exact
seam before this suite existed (owner brief, 2026-09-01). A plain synchronous call with no
``await`` inside it (:meth:`_TraceStack.adopt`) cannot genuinely race under asyncio's cooperative
model — one coroutine always runs it to completion before another starts — so that half of
invariant 7 (the adoption ceiling) is thread-only by construction; the live-child hand-over and
reset-racing-publish halves both span real await points and get both variants.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from stress_support import narrowed_switch_interval, run_barrier_synced, stress_repeat

from narrativetrace.context import ContextVarNarrativeContext, _TraceStack
from narrativetrace.groups import FireAndForgetGroup, ForkJoinGroup
from narrativetrace.ids import SpanId
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature
from narrativetrace.trace_object import trace_object

pytestmark = pytest.mark.stress

_JOIN_TIMEOUT_SECONDS = 5.0


def _count_nodes(nodes: list[TraceNode]) -> int:
    return sum(1 + _count_nodes(n.children) for n in nodes)


# --------------------------------------------------------------------------- #
# Invariant 7a — adoption ceiling: no partial batch admission                  #
# --------------------------------------------------------------------------- #
def _adopt_batch(
    stack: _TraceStack, batch: set[SpanId], results: dict[str, int], key: str
) -> Callable[[], None]:
    def run() -> None:
        results[key] = stack.adopt(batch)

    return run


def _adoption_ceiling_iteration(ceiling: int, batch_size: int) -> None:
    stack = _TraceStack(max_adopted_spans=ceiling)
    batch_a = {SpanId.generate() for _ in range(batch_size)}
    batch_b = {SpanId.generate() for _ in range(batch_size)}
    results: dict[str, int] = {}
    with narrowed_switch_interval():
        run_barrier_synced(
            [_adopt_batch(stack, batch_a, results, "a"), _adopt_batch(stack, batch_b, results, "b")]
        )

    adopted = stack.adopted_span_ids()
    assert adopted in (batch_a, batch_b)  # exactly one batch got in, whole
    assert results["a"] == 0
    assert results["b"] == 0  # neither batch was itself discarded (the stack was never closed)
    assert stack.refused_scopes == 1
    assert stack.refused_spans == batch_size  # the loser is refused whole, and counted exactly once


class TestAdoptionCeilingAllOrNothing:
    """Invariant 7: no partial batch adoption at the ceiling — a batch that would cross it is
    refused whole and counted, never partially admitted (mirrors Java's ``AdoptionCeilingTest``)."""

    def test_two_batches_racing_a_ceiling_that_fits_only_one(self) -> None:
        for _ in range(stress_repeat(quick=30, long=1500)):
            _adoption_ceiling_iteration(ceiling=4, batch_size=3)


# --------------------------------------------------------------------------- #
# Invariant 7b — live-child hand-over: capture racing scope-close               #
# --------------------------------------------------------------------------- #
def _live_child_handover_threads_iteration() -> None:
    context = ContextVarNarrativeContext()
    # Taken by the origin (this thread) before the worker exists — snapshotting from inside the
    # worker itself would make the worker's own stack the origin, not the parent's (ForkJoinGroup
    # gets this right in production: `snapshot = self._context.snapshot()` happens in the
    # launching context, before the wrapped callable ever runs on the worker).
    snapshot = context.snapshot()
    ready = threading.Event()
    proceed = threading.Event()

    def worker() -> None:
        with snapshot.activate():
            context.enter_method(MethodSignature("Svc", "work", []))
            ready.set()
            proceed.wait(timeout=_JOIN_TIMEOUT_SECONDS)
            context.exit_method_with_return("ok")

    thread = threading.Thread(target=worker)
    with narrowed_switch_interval():
        thread.start()
        assert ready.wait(timeout=_JOIN_TIMEOUT_SECONDS)
        mid_scope = _count_nodes(context.capture_trace().roots)
        proceed.set()
        thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
    after_close = _count_nodes(context.capture_trace().roots)

    assert mid_scope == 1  # visible through the live-child side while the worker is still running
    assert after_close == 1  # visible through the adopted side afterward — never 0, never 2


async def _live_child_handover_asyncio_iteration() -> None:
    context = ContextVarNarrativeContext()
    snapshot = context.snapshot()  # taken by the origin task before the worker task exists
    ready = asyncio.Event()
    proceed = asyncio.Event()

    async def worker() -> None:
        with snapshot.activate():
            context.enter_method(MethodSignature("Svc", "work", []))
            ready.set()
            await proceed.wait()
            context.exit_method_with_return("ok")

    task = asyncio.ensure_future(worker())
    await ready.wait()
    mid_scope = _count_nodes(context.capture_trace().roots)
    proceed.set()
    await task
    after_close = _count_nodes(context.capture_trace().roots)

    assert mid_scope == 1
    assert after_close == 1


class TestLiveChildHandOver:
    """Invariant 7: a capture racing a worker's scope-close sees its spans through exactly one
    side of the hand-over, never both and never neither (mirrors ``LiveChildHandOverTest``)."""

    def test_threads(self) -> None:
        for _ in range(stress_repeat(quick=15, long=400)):
            _live_child_handover_threads_iteration()

    def test_asyncio_tasks(self) -> None:
        for _ in range(stress_repeat(quick=15, long=400)):
            asyncio.run(_live_child_handover_asyncio_iteration())


# --------------------------------------------------------------------------- #
# Invariant 7c — reset racing publish                                          #
# --------------------------------------------------------------------------- #
def _request_cycle(context: ContextVarNarrativeContext, method_name: str) -> int:
    context.enter_method(MethodSignature("Svc", method_name, []))
    context.exit_method_with_return("ok")
    own = _count_nodes(context.capture_trace().roots)
    context.reset()
    return own


def _reset_race_threads_iteration() -> None:
    context = ContextVarNarrativeContext()
    results: list[int] = [0, 0]

    def make(index: int) -> Callable[[], None]:
        def run() -> None:
            results[index] = _request_cycle(context, f"m{index}")

        return run

    with narrowed_switch_interval():
        run_barrier_synced([make(0), make(1)])

    assert results == [1, 1]  # each request saw exactly its own span, never the other's
    assert context._store.events() == []  # both requests reset(): nothing left behind


async def _request_cycle_async(context: ContextVarNarrativeContext, method_name: str) -> int:
    context.enter_method(MethodSignature("Svc", method_name, []))
    await asyncio.sleep(0)  # yield: the other request's task may run its own enter/exit here
    context.exit_method_with_return("ok")
    await asyncio.sleep(0)
    own = _count_nodes(context.capture_trace().roots)
    context.reset()
    return own


async def _reset_race_asyncio_iteration() -> None:
    context = ContextVarNarrativeContext()
    a, b = await asyncio.gather(
        _request_cycle_async(context, "m0"), _request_cycle_async(context, "m1")
    )
    assert (a, b) == (1, 1)
    assert context._store.events() == []


class TestResetRacingPublish:
    """Invariant 7: reset() racing a concurrent request's own publish is safe — no cross-request
    visibility leak, and a finished request never leaves residue (mirrors
    ``ResetRacingRequestsTest``)."""

    def test_threads(self) -> None:
        for _ in range(stress_repeat(quick=20, long=500)):
            _reset_race_threads_iteration()

    def test_asyncio_tasks(self) -> None:
        for _ in range(stress_repeat(quick=20, long=500)):
            asyncio.run(_reset_race_asyncio_iteration())


# --------------------------------------------------------------------------- #
# Invariant 7, production entry point — ForkJoinGroup/FireAndForgetGroup under #
# MIXED thread + asyncio-task concurrency, racing the same group instance      #
# --------------------------------------------------------------------------- #
class _Worker:
    def do(self, label: str) -> str:
        return f"did {label}"

    async def do_async(self, label: str) -> str:
        await asyncio.sleep(0)
        return f"did {label}"


async def _fork_join_mixed_iteration(thread_count: int, task_count: int) -> None:
    context = ContextVarNarrativeContext()
    root = context.enter_method(MethodSignature("Svc", "parent", []))
    worker = trace_object(_Worker(), context)
    group = ForkJoinGroup.create(context)
    loop = asyncio.get_running_loop()

    def make_thread_task(label: str) -> Callable[[], str]:
        return group.wrap(lambda: worker.do(label))

    def make_task_future(label: str) -> Awaitable[str]:
        return group.run_async(lambda: worker.do_async(label))

    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        thread_futures = [
            loop.run_in_executor(pool, make_thread_task(f"t{i}")) for i in range(thread_count)
        ]
        task_futures = [make_task_future(f"a{i}") for i in range(task_count)]
        await asyncio.gather(*thread_futures, *task_futures)

    merged = group.merge()
    context.exit_method_with_return(None, span_id=root)

    assert len(merged) == thread_count + task_count  # every worker's subtree landed exactly once
    assert _count_nodes(context.capture_trace().roots) == 1 + len(merged)  # parent + every child


def _fire_and_forget_mixed_iteration(thread_count: int, task_count: int) -> None:
    context = ContextVarNarrativeContext()
    context.enter_method(MethodSignature("Svc", "parent", []))
    worker = trace_object(_Worker(), context)
    group = FireAndForgetGroup.create(context, "Launcher")

    def thread_worker(label: str) -> Callable[[], str]:
        return group.wrap(lambda: worker.do(label))

    async def task_worker(label: str) -> None:
        await group.run_async(lambda: worker.do_async(label))

    async def run_mixed() -> None:
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=thread_count) as pool:
            thread_futures = [
                loop.run_in_executor(pool, thread_worker(f"t{i}")) for i in range(thread_count)
            ]
            task_futures = [task_worker(f"a{i}") for i in range(task_count)]
            await asyncio.gather(*thread_futures, *task_futures)

    with narrowed_switch_interval():
        asyncio.run(run_mixed())

    roots = group.child_roots()
    assert len(roots) == thread_count + task_count  # no lost or duplicated background subtree


class TestGroupsUnderMixedConcurrency:
    """Invariant 7's production entry point: ``ForkJoinGroup``/``FireAndForgetGroup`` racing real
    OS threads and asyncio tasks against the *same* group instance at once — a combination Java's
    thread-only jcstress suite cannot exercise, and this suite's asyncio coverage exists precisely
    to close that gap."""

    def test_fork_join_group_merges_every_mixed_worker_exactly_once(self) -> None:
        for _ in range(stress_repeat(quick=10, long=150)):
            asyncio.run(_fork_join_mixed_iteration(thread_count=4, task_count=4))

    def test_fire_and_forget_group_collects_every_mixed_worker_exactly_once(self) -> None:
        for _ in range(stress_repeat(quick=10, long=150)):
            _fire_and_forget_mixed_iteration(thread_count=4, task_count=4)
