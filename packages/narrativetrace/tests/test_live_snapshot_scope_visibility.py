# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A worker's calls are reportable from the moment they are published, not from scope close.

Mirrors Java ``LiveSnapshotScopeVisibilityTest``. Adoption at scope close alone is not when the
caller looks: a framework routinely hands control back in between — Spring completes an ``@Async``
method's future *inside* the decorated task, so ``future.get()`` returns while the decorator's
scope is still open, and an asyncio task can signal completion before its ``with`` block unwinds.

No sleeping and no waiting for the worker: two latches hold it at the exact instant between "the
call is published" and "the scope closes", which is the window the race lives in.
"""

from __future__ import annotations

import gc
import threading
from collections.abc import Iterator

import pytest

from narrativetrace.context import ContextSnapshot, ContextVarNarrativeContext
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

_CALLER = MethodSignature("OrderService", "placeOrder", [])
_WORKER_CALL = MethodSignature("NotificationService", "notifyOrderPlaced", [])
_LATCH_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def ctx() -> Iterator[ContextVarNarrativeContext]:
    context = ContextVarNarrativeContext()
    yield context
    context.reset()


class TestWhileTheScopeIsOpen:
    def test_the_workers_call_is_visible_to_the_origin_while_the_scope_is_still_open(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        held = _worker_holding_its_scope_open(ctx, adopts=True)
        try:
            held.wait_until_published()

            assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced"], (
                "the caller observed the worker's completion, so its trace must already show it"
            )
        finally:
            held.release()

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced"], (
            "scope close adopts the same spans — it must not add a second copy of them"
        )

    def test_the_workers_call_nests_under_the_caller_while_the_scope_is_still_open(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        held = _worker_holding_its_scope_open(ctx, adopts=True)
        try:
            held.wait_until_published()

            roots = ctx.capture_trace().roots

            assert len(roots) == 1
            assert roots[0].signature.method_name == "placeOrder"
            assert [c.signature.method_name for c in roots[0].children] == ["notifyOrderPlaced"]
        finally:
            held.release()

    def test_a_scope_activated_without_adoption_stays_out_open_or_closed(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        held = _worker_holding_its_scope_open(ctx, adopts=False)
        try:
            held.wait_until_published()

            assert _method_names(ctx.capture_trace()) == ["placeOrder"], (
                "helpers that re-emit their own children must not have them counted twice"
            )
        finally:
            held.release()

        assert _method_names(ctx.capture_trace()) == ["placeOrder"]


class TestAfterTheScopeCloses:
    def test_closing_the_scope_ends_the_live_registration(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_CALLER)
        origin = ctx._get_stack()
        snapshot = ctx.snapshot()
        ctx.exit_method_with_return('"ORD-1"')

        _run_worker_to_completion(ctx, snapshot)

        # Asserted before live_child_span_ids(), which prunes cleared registrations as it reads:
        # the registration must be *ended* at close, not merely decay when the worker is collected.
        assert origin.live_children == set(), (
            "a finished worker's stack must not stay pinned to the origin for its whole life"
        )
        assert origin.live_child_span_ids() == set()
        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced"], (
            "adoption has taken the same spans over, so nothing is lost by unregistering"
        )

    def test_the_workers_call_survives_the_collection_of_its_stack(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_CALLER)
        snapshot = ctx.snapshot()
        ctx.exit_method_with_return('"ORD-1"')
        _run_worker_to_completion(ctx, snapshot)

        # The registry holds the child weakly, so only adoption makes the visibility permanent.
        gc.collect()

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced"]

    def test_a_snapshot_whose_origin_is_gone_is_silent_at_activation_and_at_close(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_CALLER)
        ctx.exit_method_with_return('"ORD-1"')
        snapshot = ctx.snapshot()
        ctx.reset()
        gc.collect()

        # Registration must skip a collected origin exactly as adoption does: an orphaned worker
        # must neither fail nor resurrect the stack it was launched from.
        _run_worker_to_completion(ctx, snapshot)

        assert ctx.capture_trace().roots == []


# ── the worker ──────────────────────────────────────────────────────────────


class _HeldWorker:
    """A worker that traces one call, announces it, and blocks *before* closing its scope.

    The state a framework's worker is in when the caller's future has already completed.
    """

    def __init__(self, ctx: ContextVarNarrativeContext, snapshot: ContextSnapshot, *, adopts: bool):
        self._published = threading.Event()
        self._release = threading.Event()
        self._thread = threading.Thread(
            target=lambda: self._run(ctx, snapshot, adopts=adopts), name="async-notify-1"
        )
        self._thread.start()

    def _run(
        self, ctx: ContextVarNarrativeContext, snapshot: ContextSnapshot, *, adopts: bool
    ) -> None:
        scope = snapshot.activate() if adopts else snapshot.activate_without_adoption()
        with scope:
            ctx.enter_method(_WORKER_CALL)
            ctx.exit_method_with_return("true")
            self._published.set()
            if not self._release.wait(_LATCH_TIMEOUT_SECONDS):
                raise AssertionError("the test never released the worker")

    def wait_until_published(self) -> None:
        assert self._published.wait(_LATCH_TIMEOUT_SECONDS), "the worker never published its call"

    def release(self) -> None:
        self._release.set()
        self._thread.join(_LATCH_TIMEOUT_SECONDS)


def _worker_holding_its_scope_open(ctx: ContextVarNarrativeContext, *, adopts: bool) -> _HeldWorker:
    ctx.enter_method(_CALLER)
    snapshot = ctx.snapshot()
    ctx.exit_method_with_return('"ORD-1"')
    return _HeldWorker(ctx, snapshot, adopts=adopts)


def _run_worker_to_completion(ctx: ContextVarNarrativeContext, snapshot: ContextSnapshot) -> None:
    """Runs one traced call under the snapshot on another thread and closes the scope."""

    def worker() -> None:
        with snapshot.activate():
            ctx.enter_method(_WORKER_CALL)
            ctx.exit_method_with_return("true")

    thread = threading.Thread(target=worker, name="async-notify-1")
    thread.start()
    thread.join(_LATCH_TIMEOUT_SECONDS)


def _method_names(tree: TraceTree) -> list[str]:
    names: list[str] = []
    _collect_method_names(tree.roots, names)
    return names


def _collect_method_names(nodes: list[TraceNode], names: list[str]) -> None:
    for node in nodes:
        names.append(node.signature.method_name)
        _collect_method_names(node.children, names)
