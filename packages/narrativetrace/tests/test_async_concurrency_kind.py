# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The `async` concurrency kind: the tag that makes adopted work approvable.

Follows the same rule as the Java runtime. Without it a structural artifact pins the
scheduler's dispatch order and no concurrent scenario can hold a stable baseline: the tag says
"these are siblings that
raced", so a renderer can group them and sort them by signature instead of by who happened to
start first.

The tag goes on the *first* span a thread or task opens under an activated snapshot — everything
deeper is ordinary sequential work on that worker — and is keyed by the launching span, so every
async child of one call forms one group.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator

import pytest

from narrativetrace.concurrency import ConcurrencyKind
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.export import export as export_json
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature

_JOIN_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def ctx() -> Iterator[ContextVarNarrativeContext]:
    context = ContextVarNarrativeContext()
    yield context
    context.reset()


def _sig(class_name: str, method_name: str) -> MethodSignature:
    return MethodSignature(class_name, method_name, [])


def _trace_call(ctx: ContextVarNarrativeContext, class_name: str, method_name: str) -> None:
    ctx.enter_method(_sig(class_name, method_name))
    ctx.exit_method_with_return("true")


def _run_under_snapshot(ctx: ContextVarNarrativeContext, method_name: str) -> int:
    """Traces one call on a named worker thread, returning that thread's id."""
    snapshot = ctx.snapshot()

    def worker() -> None:
        with snapshot.activate():
            _trace_call(ctx, "NotificationService", method_name)

    thread = threading.Thread(target=worker, name="async-worker")
    thread.start()
    thread.join(_JOIN_TIMEOUT_SECONDS)
    assert thread.ident is not None
    return thread.ident


def _descendants(nodes: list[TraceNode]) -> list[TraceNode]:
    found: list[TraceNode] = []
    for node in nodes:
        found.append(node)
        found += _descendants(node.children)
    return found


class TestTaggingTheAsyncBoundary:
    def test_the_first_span_a_worker_opens_under_a_snapshot_is_tagged_async(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        _run_under_snapshot(ctx, "notifyOrderPlaced")
        ctx.exit_method_with_return("OrderResult")

        adopted = ctx.capture_trace().roots[0].children[0]

        assert adopted.concurrency is not None
        assert adopted.concurrency.kind is ConcurrencyKind.ASYNC

    def test_the_first_span_an_asyncio_task_opens_under_a_snapshot_is_tagged_async(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        async def scenario() -> TraceNode:
            ctx.enter_method(_sig("OrderService", "placeOrder"))
            snapshot = ctx.snapshot()

            async def worker() -> None:
                with snapshot.activate():
                    _trace_call(ctx, "NotificationService", "notifyOrderPlaced")

            await asyncio.create_task(worker())
            ctx.exit_method_with_return("OrderResult")
            return ctx.capture_trace().roots[0].children[0]

        adopted = asyncio.run(scenario())

        assert adopted.concurrency is not None
        assert adopted.concurrency.kind is ConcurrencyKind.ASYNC

    def test_everything_deeper_on_that_worker_is_ordinary_sequential_work(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        snapshot = ctx.snapshot()

        def worker() -> None:
            with snapshot.activate():
                ctx.enter_method(_sig("NotificationService", "notifyOrderPlaced"))
                _trace_call(ctx, "EmailGateway", "send")
                ctx.exit_method_with_return("true")

        thread = threading.Thread(target=worker, name="async-worker")
        thread.start()
        thread.join(_JOIN_TIMEOUT_SECONDS)

        root = ctx.capture_trace().roots[0]
        assert root.concurrency is not None
        assert root.children[0].concurrency is None

    def test_a_call_on_the_launching_execution_context_carries_no_concurrency_info(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        _trace_call(ctx, "OrderService", "placeOrder")

        assert ctx.capture_trace().roots[0].concurrency is None

    def test_the_tag_names_the_worker_that_ran_the_call(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """Whole identity, not just the name: an exporter writes all three fields."""
        worker_id = _run_under_snapshot(ctx, "notifyOrderPlaced")

        concurrency = ctx.capture_trace().roots[0].concurrency
        assert concurrency is not None
        assert concurrency.thread_name == "async-worker"
        assert concurrency.thread_id == worker_id
        assert concurrency.virtual is False


class TestGrouping:
    def test_async_children_of_one_call_share_one_group(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """Keyed by the launching span, so a renderer can present them as one raced set."""
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        _run_under_snapshot(ctx, "notifyOrderPlaced")
        _run_under_snapshot(ctx, "notifyWarehouse")
        ctx.exit_method_with_return("OrderResult")

        children = ctx.capture_trace().roots[0].children
        groups = {c.concurrency.group_id for c in children if c.concurrency is not None}

        assert len(children) == 2
        assert len(groups) == 1

    def test_work_propagated_with_no_parent_span_groups_by_trace(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """A parentless async root still needs a group; the trace is the only key left."""
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        ctx.exit_method_with_return("OrderResult")
        trace_id = ctx.trace_id()

        _run_under_snapshot(ctx, "notifyOrderPlaced")

        adopted = ctx.capture_trace().roots[1]
        assert adopted.concurrency is not None
        assert adopted.concurrency.group_id == f"async-{trace_id}"

    def test_two_calls_launched_from_different_spans_do_not_share_a_group(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        _run_under_snapshot(ctx, "notifyOrderPlaced")
        ctx.exit_method_with_return("OrderResult")
        ctx.enter_method(_sig("OrderService", "cancelOrder"))
        _run_under_snapshot(ctx, "notifyCancelled")
        ctx.exit_method_with_return("OrderResult")

        tagged = [n for n in _descendants(ctx.capture_trace().roots) if n.concurrency is not None]
        groups = {n.concurrency.group_id for n in tagged if n.concurrency is not None}

        assert len(tagged) == 2
        assert len(groups) == 2


class TestCanonicalExport:
    def test_the_json_export_carries_the_async_kind(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        _run_under_snapshot(ctx, "notifyOrderPlaced")
        ctx.exit_method_with_return("OrderResult")

        exported = json.loads(export_json(ctx.capture_trace()))

        kinds = [e["concurrency"]["kind"] for e in exported["events"] if "concurrency" in e]
        assert kinds == ["async"]
