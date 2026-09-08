# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The nested chain: origin → worker → grandchild, where the worker snapshots its own stack.

Mirrors Java ``NestedChainAdoptionTest``. Adoption and live visibility that carry a child's *own*
spans only stop one hop short: the grandchild's call reaches the worker and dies there, invisible
to the origin — the execution context whose request this is, and the only one anyone captures on.
Two async hops is not exotic: a controller dispatches to a service that dispatches to a client.

Three latches, no sleeping. The grandchild publishes and blocks before closing its scope; the
worker blocks before closing its own. That holds the chain at each instant that matters, and the
same tree is asserted at all of them, so a span that appears and then vanishes — or is counted
twice — fails.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager

import pytest

from narrativetrace.context import ContextSnapshot, ContextVarNarrativeContext
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

_ORIGIN_CALL = MethodSignature("OrderService", "placeOrder", [])
_WORKER_CALL = MethodSignature("NotificationService", "notifyOrderPlaced", [])
_GRANDCHILD_CALL = MethodSignature("EmailGateway", "send", [])
_LATCH_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def ctx() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext()


@pytest.fixture
def chain(ctx: ContextVarNarrativeContext) -> Iterator[_Chain]:
    running = _Chain()
    yield running
    running.release_everything()
    ctx.reset()


class TestTheChainReachesTheOrigin:
    def test_the_grandchilds_call_is_visible_to_the_origin_while_every_scope_is_still_open(
        self, ctx: ContextVarNarrativeContext, chain: _Chain
    ) -> None:
        """Two async hops from the origin is still the origin's request."""
        chain.start_from(ctx)

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced", "send"]

    def test_the_grandchilds_call_stays_visible_once_its_own_scope_closes(
        self, ctx: ContextVarNarrativeContext, chain: _Chain
    ) -> None:
        """The worker adopted it; the origin must see it through the worker either way."""
        chain.start_from(ctx)

        chain.close_grandchild()

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced", "send"]

    def test_the_grandchilds_call_stays_visible_once_every_scope_closes(
        self, ctx: ContextVarNarrativeContext, chain: _Chain
    ) -> None:
        """Hand-over must carry what the child adopted, not only what it created."""
        chain.start_from(ctx)

        chain.close_grandchild()
        chain.close_worker()

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced", "send"]

    def test_the_worker_closing_before_its_grandchild_still_hands_the_grandchild_over(
        self, ctx: ContextVarNarrativeContext, chain: _Chain
    ) -> None:
        chain.start_from(ctx)

        # The order a framework actually produces when the outer task returns first: the worker's
        # scope closes while its own child is still running.
        chain.close_worker()

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced", "send"]

        chain.close_grandchild()

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced", "send"], (
            "nothing may appear twice once the late grandchild finishes"
        )

    def test_the_calls_nest_origin_to_worker_to_grandchild(
        self, ctx: ContextVarNarrativeContext, chain: _Chain
    ) -> None:
        chain.start_from(ctx)
        chain.close_grandchild()
        chain.close_worker()

        roots = ctx.capture_trace().roots

        assert len(roots) == 1
        assert roots[0].signature.method_name == "placeOrder"
        worker = roots[0].children
        assert len(worker) == 1
        assert worker[0].signature.method_name == "notifyOrderPlaced"
        assert [c.signature.method_name for c in worker[0].children] == ["send"]

    def test_every_call_in_the_chain_carries_the_origins_trace_id(
        self, ctx: ContextVarNarrativeContext, chain: _Chain
    ) -> None:
        """The whole chain inherits one trace id through the snapshots; adoption changes only
        which spans the origin considers reportable, never which context stamps a span."""
        chain.start_from(ctx)
        chain.close_grandchild()
        chain.close_worker()

        trace_ids = _trace_ids(ctx.capture_trace())

        assert len(trace_ids) == 3
        assert set(trace_ids) == {trace_ids[0]}


class TestUnadoptedHops:
    """Both exclusion cases: a helper that publishes its own children owns them alone."""

    def test_a_grandchild_behind_an_unadopting_worker_reaches_neither_the_worker_nor_the_origin(
        self, ctx: ContextVarNarrativeContext, chain: _Chain
    ) -> None:
        chain.with_worker_adoption(adopts=False).start_from(ctx)

        assert _method_names(ctx.capture_trace()) == ["placeOrder"]

        chain.close_grandchild()
        chain.close_worker()

        assert _method_names(ctx.capture_trace()) == ["placeOrder"]

    def test_a_grandchild_activated_without_adoption_stays_out_of_the_origins_trace(
        self, ctx: ContextVarNarrativeContext, chain: _Chain
    ) -> None:
        chain.with_grandchild_adoption(adopts=False).start_from(ctx)

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced"]

        chain.close_grandchild()
        chain.close_worker()

        assert _method_names(ctx.capture_trace()) == ["placeOrder", "notifyOrderPlaced"]


# ── the chain ───────────────────────────────────────────────────────────────


class _Chain:
    """Two threads held open by latches: the worker snapshots the origin, the grandchild the worker.

    Each blocks after publishing its call and closes only when released, so a test controls which
    scopes are open at the moment it captures.
    """

    def __init__(self) -> None:
        self._grandchild_published = threading.Event()
        self._release_grandchild = threading.Event()
        self._grandchild_closed = threading.Event()
        self._release_worker = threading.Event()
        self._worker_closed = threading.Event()
        self._worker_adopts = True
        self._grandchild_adopts = True
        self._worker: threading.Thread | None = None
        self._grandchild: threading.Thread | None = None

    def with_worker_adoption(self, *, adopts: bool) -> _Chain:
        self._worker_adopts = adopts
        return self

    def with_grandchild_adoption(self, *, adopts: bool) -> _Chain:
        self._grandchild_adopts = adopts
        return self

    def start_from(self, ctx: ContextVarNarrativeContext) -> None:
        """Traces the origin call, launches the chain, returns once the grandchild has published."""
        ctx.enter_method(_ORIGIN_CALL)
        snapshot = ctx.snapshot()
        ctx.exit_method_with_return('"ORD-1"')

        self._worker = threading.Thread(
            target=lambda: self._run_worker(ctx, snapshot), name="async-notify-1"
        )
        self._worker.start()
        _await(self._grandchild_published, "the grandchild never published its call")

    def _run_worker(self, ctx: ContextVarNarrativeContext, snapshot: ContextSnapshot) -> None:
        """Deliberately does *not* join its grandchild before closing.

        A worker whose own scope ends while its child is still running is the ordering a framework
        actually produces, and it is the ordering that decides whether hand-over carries the chain.
        """
        with _activation(snapshot, adopts=self._worker_adopts):
            ctx.enter_method(_WORKER_CALL)
            nested = ctx.snapshot()
            ctx.exit_method_with_return("true")
            self._grandchild = threading.Thread(
                target=lambda: self._run_grandchild(ctx, nested), name="async-email-1"
            )
            self._grandchild.start()
            _await(self._release_worker, "the test never released the worker")
        self._worker_closed.set()

    def _run_grandchild(self, ctx: ContextVarNarrativeContext, snapshot: ContextSnapshot) -> None:
        with _activation(snapshot, adopts=self._grandchild_adopts):
            ctx.enter_method(_GRANDCHILD_CALL)
            ctx.exit_method_with_return("true")
            self._grandchild_published.set()
            _await(self._release_grandchild, "the test never released the grandchild")
        self._grandchild_closed.set()

    def close_grandchild(self) -> None:
        self._release_grandchild.set()
        _await(self._grandchild_closed, "the grandchild never closed its scope")

    def close_worker(self) -> None:
        self._release_worker.set()
        _await(self._worker_closed, "the worker never closed its scope")

    def release_everything(self) -> None:
        self._release_grandchild.set()
        self._release_worker.set()
        for thread in (self._worker, self._grandchild):
            if thread is not None:
                thread.join(_LATCH_TIMEOUT_SECONDS)


def _activation(snapshot: ContextSnapshot, *, adopts: bool) -> AbstractContextManager[None]:
    return snapshot.activate() if adopts else snapshot.activate_without_adoption()


def _await(latch: threading.Event, complaint: str) -> None:
    if not latch.wait(_LATCH_TIMEOUT_SECONDS):
        raise AssertionError(complaint)


def _method_names(tree: TraceTree) -> list[str]:
    names: list[str] = []
    _collect_method_names(tree.roots, names)
    return names


def _collect_method_names(nodes: list[TraceNode], names: list[str]) -> None:
    for node in nodes:
        names.append(node.signature.method_name)
        _collect_method_names(node.children, names)


def _trace_ids(tree: TraceTree) -> list[str]:
    ids: list[str] = []
    _collect_trace_ids(tree.roots, ids)
    return ids


def _collect_trace_ids(nodes: list[TraceNode], ids: list[str]) -> None:
    for node in nodes:
        if node.span_context is not None:
            ids.append(str(node.span_context.trace_id))
        _collect_trace_ids(node.children, ids)
