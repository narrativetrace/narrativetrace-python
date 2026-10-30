# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-211: spans that no execution context ever captures or resets are released, and handed-over
work is captured exactly as before.

Mirrors Java ``UnownedSpanReleaseTest``. The review of 2026-10-27 measured an unbounded leak: an
execution context nobody resets (an unwrapped pool worker, a raw thread, an asyncio task that never
captures) kept every span it traced in the context's span map and its own known-span set, and every
event in the store (Python's store is written on the caller's thread, so no flush is needed for
that half); a pooled thread kept one trace id for life. The shapes here are that review's scratch
experiments (``AgentOnly``, ``ProdLeak``, ``E1``-``E3``) made bounded and fast: the
unowned-retention limit is lowered through the ``_unowned_span_limit`` seam, so a few thousand
iterations cross it many times over, and every assertion is a constant bound, never a timing.

Retention is state a caller cannot see, so the assertions read ``_span_contexts``, the stack's
``known`` set and the store beside the public capture.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor

import pytest

from narrativetrace.context import ContextVarNarrativeContext, _TraceStack
from narrativetrace.events import EnterEvent, span_id_of
from narrativetrace.groups import ForkJoinGroup
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature
from narrativetrace.trace_object import trace_object
from narrativetrace.tree import TraceTree

LIMIT = 64
"""The unowned-retention limit these tests run under: small, so it is crossed many times."""

ITERATIONS = 2_000
"""Iterations of unowned work: thirty times the limit's worth of spans and more."""

BOUND = 4 * LIMIT
"""What "bounded" means here: the limit, plus the latest root of each live execution context
(never released, so a later capture there sees it whole), with room to spare -- and two orders of
magnitude below what the unfixed code retains after :data:`ITERATIONS`."""

_TRACE_ID = TraceId.generate()
"""An inbound trace id for the adopt-claims case."""

_WAIT_SECONDS = 10.0
"""A hang guard on joins and futures, never a tolerance: every wait here ends on completion."""


@pytest.fixture
def ctx() -> Iterator[ContextVarNarrativeContext]:
    context = ContextVarNarrativeContext()
    context._unowned_span_limit = LIMIT
    yield context
    context.reset()


@pytest.fixture
def pool() -> Iterator[ThreadPoolExecutor]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="app-pool")
    yield executor
    executor.shutdown(wait=True)


# ------------------------------------------------------------------------- the leak, bounded


def test_agent_only_shape_a_thread_nobody_captures_keeps_a_bounded_number_of_spans(
    ctx: ContextVarNarrativeContext,
) -> None:
    for _ in range(ITERATIONS):
        _call(ctx, "Svc", "work")

    assert len(ctx._span_contexts) <= BOUND, "span contexts are released when their span exits"
    assert len(ctx._get_stack().known) <= BOUND, (
        "the thread's own known-span set stays bounded without any capture or reset"
    )
    assert _distinct_stored_spans(ctx) <= BOUND, "and so does the store it writes to"


def test_emitted_roots_on_a_thread_nobody_captures_keep_a_bounded_number_of_spans(
    ctx: ContextVarNarrativeContext,
) -> None:
    retained: list[tuple[int, int]] = []

    def emit_roots() -> None:
        for _ in range(ITERATIONS):
            ctx.emit_trace_node(TraceNode(_sig("Emitted", "root")), None)
        retained.append((len(ctx._get_stack().known), _distinct_stored_spans(ctx)))

    _run_on_raw_thread(emit_roots)

    assert retained, "the raw thread finished emitting"
    known, stored = retained[0]
    assert known <= BOUND, f"emitted roots are sealed into the release: {known} known ids"
    assert stored <= BOUND, f"and so is the store they were written to: {stored} stored spans"


def test_agent_only_shape_through_the_proxy_sync_and_async(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    """The same shape through ``trace_object`` -- the decorator path exits by span id after a
    scoped call, sync and async -- on a pool thread and in an asyncio task nobody captures."""
    service = trace_object(_Service(), ctx)

    def sync_loop() -> int:
        for _ in range(ITERATIONS):
            service.work()
        return len(ctx._get_stack().known)

    async def async_loop() -> int:
        for _ in range(ITERATIONS):
            await service.awork()
        return len(ctx._get_stack().known)

    assert pool.submit(sync_loop).result(_WAIT_SECONDS) <= BOUND
    assert pool.submit(lambda: asyncio.run(async_loop())).result(_WAIT_SECONDS) <= BOUND
    assert len(ctx._span_contexts) <= BOUND
    assert _distinct_stored_spans(ctx) <= BOUND


def test_prod_leak_shape_unwrapped_pool_and_raw_thread_work_leaves_a_bounded_store(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    for i in range(1, ITERATIONS + 1):
        ctx.reset()
        _call(ctx, "Request", "handle")
        pool.submit(_call, ctx, "Pool", "work").result(_WAIT_SECONDS)
        if i % 2 == 0:
            _run_on_raw_thread(lambda: _call(ctx, "Raw", "work"))
        assert sorted(_names(ctx.capture_trace())) == ["Request.handle", "Request.inner"], (
            "each request's capture is exactly its own work, as before"
        )
        ctx.reset()

    assert _distinct_stored_spans(ctx) <= BOUND, (
        "unhanded-over events no longer accumulate in the store"
    )
    assert len(ctx._span_contexts) <= BOUND
    assert pool.submit(lambda: len(ctx._get_stack().known)).result(_WAIT_SECONDS) <= BOUND, (
        "the pool thread's own known-span set stays bounded"
    )


def test_two_consecutive_roots_on_an_unowned_pooled_thread_are_two_traces(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    pool.submit(_call, ctx, "Pool", "first").result(_WAIT_SECONDS)
    pool.submit(_call, ctx, "Pool", "second").result(_WAIT_SECONDS)

    roots = _root_enters_on(ctx, "app-pool")
    assert len(roots) == 2
    assert roots[0].span_context.trace_id != roots[1].span_context.trace_id, (
        "a pooled thread nobody hands over must not correlate unrelated work"
    )
    assert roots[1].span_context.story_id == "Pool.second", (
        "and its next story is its next root's, not the first one it ever ran"
    )


def test_asking_for_the_trace_id_between_roots_continues_that_trace(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    pool.submit(_call, ctx, "Pool", "first").result(_WAIT_SECONDS)
    asked = pool.submit(ctx.trace_id).result(_WAIT_SECONDS)
    pool.submit(_call, ctx, "Pool", "second").result(_WAIT_SECONDS)

    roots = _root_enters_on(ctx, "app-pool")
    assert asked == roots[0].span_context.trace_id == roots[1].span_context.trace_id, (
        "the id asked for is the trace the thread is in, and the next root continues it"
    )


def test_a_snapshot_between_roots_continues_that_trace(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    pool.submit(_call, ctx, "Pool", "first").result(_WAIT_SECONDS)
    pool.submit(ctx.snapshot).result(_WAIT_SECONDS)
    pool.submit(_call, ctx, "Pool", "second").result(_WAIT_SECONDS)

    roots = _root_enters_on(ctx, "app-pool")
    assert roots[0].span_context.trace_id == roots[1].span_context.trace_id


def test_a_pooled_task_that_reads_its_trace_id_before_any_call_continues_the_task_before_it(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    """B-217 (pinning, not a fix): the core cannot tell the work at hand asking for its own
    identity (the supported handover case) from the next unrelated task that happened to ask
    first -- both look identical from a stack nobody claimed. Documented in
    ``documentation/choosing-an-integration.md``."""
    pool.submit(_call, ctx, "Pool", "first").result(_WAIT_SECONDS)
    first_id = _root_enters_on(ctx, "app-pool")[0].span_context.trace_id

    second_id = pool.submit(ctx.trace_id).result(_WAIT_SECONDS)

    assert second_id == first_id, (
        "an unrelated task that only reads its id before tracing anything inherits the task "
        "before it"
    )


def test_a_pooled_task_that_takes_a_snapshot_before_any_call_continues_the_task_before_it(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    """B-217 (pinning): the same limitation through ``snapshot()``."""
    pool.submit(_call, ctx, "Pool", "first").result(_WAIT_SECONDS)
    pool.submit(ctx.snapshot).result(_WAIT_SECONDS)
    pool.submit(_call, ctx, "Pool", "second").result(_WAIT_SECONDS)

    roots = _root_enters_on(ctx, "app-pool")
    assert roots[1].span_context.trace_id == roots[0].span_context.trace_id, (
        "taking a snapshot before any call still continues the task before it"
    )


def test_work_handed_over_through_a_snapshot_gives_the_pooled_task_a_fresh_identity(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    """B-217, supported answer (i): the handed-over work carries the handing-over thread's
    trace, never the pool's leftover one."""
    pool.submit(_call, ctx, "Pool", "first").result(_WAIT_SECONDS)
    first_id = _root_enters_on(ctx, "app-pool")[0].span_context.trace_id

    request_id = ctx.trace_id()
    handed_over = ctx.snapshot()
    carried = pool.submit(handed_over.wrap(ctx.trace_id)).result(_WAIT_SECONDS)

    assert carried == request_id
    assert carried != first_id


def test_resetting_at_task_start_gives_the_pooled_task_a_fresh_identity(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    """B-217, supported answer (ii): ``reset()`` claims the thread, so the task starts over
    instead of inheriting the trace the last unowned root left armed."""
    pool.submit(_call, ctx, "Pool", "first").result(_WAIT_SECONDS)
    first_id = _root_enters_on(ctx, "app-pool")[0].span_context.trace_id

    def task() -> TraceId:
        ctx.reset()
        return ctx.trace_id()

    assert pool.submit(task).result(_WAIT_SECONDS) != first_id


def test_evicted_spans_are_counted_on_their_own_stack_and_nowhere_else(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    roots = 10 * LIMIT
    for _ in range(roots):
        _call(ctx, "Svc", "work")

    def bystander() -> tuple[TraceTree, int]:
        ctx.reset()
        _call(ctx, "Bystander", "work")
        return ctx.capture_trace(), ctx.trace_loss().refused_spans

    bystander_tree, bystander_refused = pool.submit(bystander).result(_WAIT_SECONDS)

    tree = ctx.capture_trace()

    missing = 2 * roots - len(_names(tree))
    assert missing > 0, "the oldest unowned roots were released"
    loss = ctx.trace_loss()
    assert loss.refused_spans == missing, (
        "and what this thread can no longer report is counted here, exactly"
    )
    assert len(_names(bystander_tree)) == 2
    assert bystander_refused == 0, "another thread's narrative lost nothing and is told nothing"
    assert loss.discarded_spans == 0


# --------------------------------------------------------------- owned work, unchanged


def test_a_claimed_thread_keeps_one_trace_and_loses_nothing_past_the_limit(
    ctx: ContextVarNarrativeContext,
) -> None:
    ctx.reset()
    roots = 5 * LIMIT
    for _ in range(roots):
        _call(ctx, "Svc", "work")

    tree = ctx.capture_trace()

    assert len(tree.roots) == roots
    assert len({r.span_context.trace_id for r in tree.roots if r.span_context}) == 1, (
        "a thread its owner resets is one trace between resets, as before"
    )
    assert ctx.trace_loss().refused_spans == 0


@pytest.mark.parametrize(
    "claim",
    [
        pytest.param(lambda c: c.reset(), id="reset"),
        pytest.param(lambda c: c.capture_trace(), id="capture"),
        pytest.param(lambda c: c.trace_loss(), id="trace_loss"),
        pytest.param(lambda c: c.clear_local_trace(), id="clear_local_trace"),
        pytest.param(lambda c: c.set_request_context("GET", None, None), id="request_context"),
        pytest.param(lambda c: c.set_user_context(None, None, None), id="user_context"),
        pytest.param(lambda c: c.adopt_trace_id(_TRACE_ID), id="adopt_trace_id"),
    ],
)
def test_every_capture_facing_call_claims_the_thread(
    ctx: ContextVarNarrativeContext, claim: Callable[[ContextVarNarrativeContext], object]
) -> None:
    claim(ctx)
    roots = 5 * LIMIT
    for _ in range(roots):
        _call(ctx, "Svc", "work")

    assert len(ctx.capture_trace().roots) == roots
    assert ctx.trace_loss().refused_spans == 0


def test_roots_queued_before_a_claim_are_kept_once_the_thread_is_claimed(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    """A segment whose stack was claimed after it was queued is dropped from the queue, never
    released: the owner now keeps it until its reset."""
    early_roots = LIMIT // 4

    def unowned_then_claimed() -> None:
        for _ in range(early_roots):
            _call(ctx, "Early", "work")
        ctx.set_request_context("GET", None, None)

    pool.submit(unowned_then_claimed).result(_WAIT_SECONDS)
    for _ in range(10 * LIMIT):
        _call(ctx, "Noise", "work")

    names, refused = pool.submit(
        lambda: (_names(ctx.capture_trace()), ctx.trace_loss().refused_spans)
    ).result(_WAIT_SECONDS)
    assert len(names) == 2 * early_roots
    assert refused == 0


def test_a_claimed_stack_refuses_eviction_and_an_empty_segment_seals_nothing() -> None:
    """The stack-level guards a release pass relies on: a stack claimed between the pass's check
    and its eviction keeps its spans, and a root that pushed nothing arms no fresh trace."""
    stack = _TraceStack()
    assert stack.seal_segment() == []
    assert not stack.fresh_trace_pending
    span_id = SpanId.generate()
    stack.push_active(span_id)
    stack.claim()
    assert stack.evict([span_id]) is None
    assert span_id in stack.known
    assert stack.refused_spans == 0


def test_a_capture_before_any_claim_still_sees_everything_under_the_limit(
    ctx: ContextVarNarrativeContext,
) -> None:
    _call(ctx, "Svc", "first")
    _call(ctx, "Svc", "second")

    assert sorted(_names(ctx.capture_trace())) == sorted(
        ["Svc.first", "Svc.inner", "Svc.second", "Svc.inner"]
    )


def test_the_latest_root_of_a_live_thread_is_never_released_even_when_larger_than_the_limit(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    root = ctx.enter_method(_sig("Big", "root"))
    for _ in range(3 * LIMIT):
        ctx.enter_method(_sig("Big", "child"))
        ctx.exit_method_with_return('"ok"')
    ctx.exit_method_with_return('"ok"', None, root)
    for _ in range(10 * LIMIT):
        pool.submit(_call, ctx, "Noise", "work").result(_WAIT_SECONDS)

    tree = ctx.capture_trace()

    assert len(tree.roots) == 1
    assert len(tree.roots[0].children) == 3 * LIMIT
    assert ctx.trace_loss().refused_spans == 0


def test_an_asyncio_task_capturing_before_any_claim_sees_its_latest_root_whole(
    ctx: ContextVarNarrativeContext, pool: ThreadPoolExecutor
) -> None:
    """Python's "live thread" is a live execution context: a running task's stack is reachable
    from its context, so its latest root is kept however much unowned noise crosses the limit."""

    async def task() -> list[str]:
        _call(ctx, "Task", "first")
        for _ in range(10 * LIMIT):
            await asyncio.wrap_future(pool.submit(_call, ctx, "Noise", "work"))
        return _names(ctx.capture_trace())

    assert sorted(asyncio.run(task())) == ["Task.first", "Task.inner"]


_HANDED_OVER = sorted(
    [
        "Test.main",
        "Fork.a",
        "Fork.inner",
        "Fork.b",
        "Fork.inner",
        "Snap.w",
        "Snap.inner",
        "Live.w",
        "Live.inner",
    ]
)
"""A fork merged under the root, a snapshot-wrapped raw thread and a live child still in scope."""


def test_handed_over_work_is_captured_exactly_as_before_under_unowned_noise(
    ctx: ContextVarNarrativeContext,
) -> None:
    noise = ThreadPoolExecutor(max_workers=2, thread_name_prefix="noise")
    release_live = threading.Event()
    try:
        tree = _handed_over_under_noise(ctx, noise, release_live)

        assert sorted(_names(tree)) == _HANDED_OVER
        loss = ctx.trace_loss()
        assert loss.refused_spans + loss.discarded_spans == 0
    finally:
        release_live.set()
        noise.shutdown(wait=True)


def _handed_over_under_noise(
    ctx: ContextVarNarrativeContext, noise: ThreadPoolExecutor, release_live: threading.Event
) -> TraceTree:
    """Every handover path under one claimed root, with unowned noise crossing the limit between
    them; captured while the live child is still inside its scope."""
    _flood(ctx, noise, 10 * LIMIT)
    ctx.reset()
    root = ctx.enter_method(_sig("Test", "main"))
    _fork_and_merge(ctx, "Fork", "a", "b")
    _flood(ctx, noise, 10 * LIMIT)
    _run_on_raw_thread(ctx.snapshot().wrap(lambda: _call(ctx, "Snap", "w")))
    live_thread = _start_live_child(ctx, release_live)
    _flood(ctx, noise, 10 * LIMIT)
    ctx.exit_method_with_return('"ok"', None, root)

    tree = ctx.capture_trace()
    release_live.set()
    live_thread.join(_WAIT_SECONDS)
    return tree


def test_concurrent_claimed_threads_sharing_a_pool_capture_only_their_own_work(
    ctx: ContextVarNarrativeContext,
) -> None:
    threads = 4
    shared = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="shared")
    barrier = threading.Barrier(threads, timeout=_WAIT_SECONDS)
    failures: list[str] = []
    runners = [
        threading.Thread(
            target=_run_rounds, args=(ctx, f"P{t}", shared, barrier, failures), name=f"runner-P{t}"
        )
        for t in range(threads)
    ]
    try:
        for runner in runners:
            runner.start()
        for runner in runners:
            runner.join(6 * _WAIT_SECONDS)
        assert failures == [], "every capture holds exactly its own handed-over work"
    finally:
        shared.shutdown(wait=True)


def _run_rounds(
    ctx: ContextVarNarrativeContext,
    tag: str,
    shared: ThreadPoolExecutor,
    barrier: threading.Barrier,
    failures: list[str],
) -> None:
    """One claimed thread of the parallel shape (the review's E3): per round, its own root, a fork
    and a snapshot task on the shared pool (handed over), an unwrapped task on the same pool and a
    raw thread (not handed over); its capture must hold exactly the handed-over work."""
    expected = sorted([f"{tag}.main", f"{tag}.fork", f"{tag}.inner", f"{tag}.snap", f"{tag}.inner"])
    try:
        for round_number in range(20):
            ctx.reset()
            barrier.wait()
            captured = _one_round(ctx, tag, shared)
            if sorted(captured) != expected:
                failures.append(f"{tag} round {round_number}: {captured}")
        ctx.reset()
    except Exception as exc:  # reported through `failures`, asserted on the test thread
        failures.append(f"{tag}: {exc!r}")


def _one_round(ctx: ContextVarNarrativeContext, tag: str, shared: ThreadPoolExecutor) -> list[str]:
    root = ctx.enter_method(_sig(tag, "main"))
    group = ForkJoinGroup.create(ctx)
    fork = shared.submit(group.wrap(lambda: _call(ctx, tag, "fork")))
    snap = shared.submit(ctx.snapshot().wrap(lambda: _call(ctx, tag, "snap")))
    unwrapped = shared.submit(_call, ctx, tag, "unwrapped")
    for future in (fork, snap, unwrapped):
        future.result(_WAIT_SECONDS)
    _run_on_raw_thread(lambda: _call(ctx, tag, "raw"))
    group.merge()
    ctx.exit_method_with_return('"ok"', None, root)
    return _names(ctx.capture_trace())


# ------------------------------------------------------------------------------- helpers


class _Service:
    def work(self) -> str:
        return "done"

    async def awork(self) -> str:
        return "done"


def _call(ctx: ContextVarNarrativeContext, class_name: str, method_name: str) -> None:
    """One root with one child: the two-span shape every review experiment used."""
    ctx.enter_method(_sig(class_name, method_name))
    ctx.enter_method(_sig(class_name, "inner"))
    ctx.exit_method_with_return('"done"')
    ctx.exit_method_with_return('"done"')


def _fork_and_merge(
    ctx: ContextVarNarrativeContext, class_name: str, first: str, second: str
) -> None:
    """Two ForkJoinGroup members on a two-thread executor, merged under the current span."""
    with ThreadPoolExecutor(max_workers=2) as forkers:
        group = ForkJoinGroup.create(ctx)
        a = forkers.submit(group.wrap(lambda: _call(ctx, class_name, first)))
        b = forkers.submit(group.wrap(lambda: _call(ctx, class_name, second)))
        a.result(_WAIT_SECONDS)
        b.result(_WAIT_SECONDS)
        group.merge()


def _start_live_child(
    ctx: ContextVarNarrativeContext, release: threading.Event
) -> threading.Thread:
    """A snapshot-activated worker that has finished its calls and is still inside its scope."""
    live = ctx.snapshot()
    entered = threading.Event()

    def body() -> None:
        with live.activate():
            _call(ctx, "Live", "w")
            entered.set()
            release.wait(_WAIT_SECONDS)

    thread = threading.Thread(target=body, name="live-child")
    thread.start()
    assert entered.wait(_WAIT_SECONDS)
    return thread


def _flood(ctx: ContextVarNarrativeContext, executor: ThreadPoolExecutor, roots: int) -> None:
    futures: list[Future[None]] = [
        executor.submit(_call, ctx, "Noise", "work") for _ in range(roots)
    ]
    for future in futures:
        future.result(_WAIT_SECONDS)


def _run_on_raw_thread(task: Callable[[], object]) -> None:
    thread = threading.Thread(target=task, name="raw")
    thread.start()
    thread.join(_WAIT_SECONDS)


def _root_enters_on(ctx: ContextVarNarrativeContext, thread_prefix: str) -> list[EnterEvent]:
    return [
        e
        for e in ctx._store.events()
        if isinstance(e, EnterEvent)
        and e.thread is not None
        and e.thread.name.startswith(thread_prefix)
        and e.span_context.parent_span_id is None
    ]


def _distinct_stored_spans(ctx: ContextVarNarrativeContext) -> int:
    ids: set[SpanId] = set()
    for event in ctx._store.events():
        span_id = span_id_of(event)
        if span_id is not None:
            ids.add(span_id)
    return len(ids)


def _names(tree: TraceTree) -> list[str]:
    names: list[str] = []
    for root in tree.roots:
        _collect(root, names)
    return names


def _collect(node: TraceNode, names: list[str]) -> None:
    names.append(f"{node.signature.class_name}.{node.signature.method_name}")
    for child in node.children:
        _collect(child, names)


def _sig(class_name: str, method_name: str) -> MethodSignature:
    return MethodSignature(class_name, method_name, [])
