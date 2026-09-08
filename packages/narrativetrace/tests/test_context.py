# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for ContextVarNarrativeContext, snapshots, and the no-op context."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager

import pytest

from narrativetrace.context import NOOP_CONTEXT, ContextSnapshot, ContextVarNarrativeContext
from narrativetrace.ids import TraceId
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel
from narrativetrace.metadata import ClientIp, EnduserId, HttpRoute, SessionId, TenantId
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.values import IntVal


def _sig(cls: str, method: str, *params: ParameterCapture) -> MethodSignature:
    return MethodSignature(cls, method, list(params))


@contextmanager
def _recording_scope(entered: list[str]) -> Iterator[None]:
    entered.append("enter")
    try:
        yield
    finally:
        entered.append("exit")


@pytest.fixture
def ctx() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext()


class TestBasicCapture:
    def test_enter_exit_produces_tree(self, ctx: ContextVarNarrativeContext) -> None:
        span = ctx.enter_method(_sig("Svc", "run"))
        assert span is not None
        ctx.exit_method_with_return("42")
        tree = ctx.capture_trace()
        assert len(tree.roots) == 1
        node = tree.roots[0]
        assert node.signature.method_name == "run"
        assert isinstance(node.outcome, Returned)
        assert node.outcome.rendered_value == "42"

    def test_nested_calls_nest_in_tree(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig("Svc", "outer"))
        ctx.enter_method(_sig("Svc", "inner"))
        ctx.exit_method_with_return("i")
        ctx.exit_method_with_return("o")
        tree = ctx.capture_trace()
        assert tree.roots[0].children[0].signature.method_name == "inner"

    def test_exception_exit_records_threw(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig("Svc", "run"))
        err = ValueError("boom")
        ctx.exit_method_with_exception(err, "failed to run")
        node = ctx.capture_trace().roots[0]
        assert isinstance(node.outcome, Threw)
        assert node.outcome.exception is err
        assert node.signature.error_context == "failed to run"

    def test_structured_return_value_preserved(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig("Svc", "run"))
        ctx.exit_method_with_return("42", IntVal(42))
        outcome = ctx.capture_trace().roots[0].outcome
        assert isinstance(outcome, Returned)
        assert outcome.structured_value == IntVal(42)

    def test_exit_on_empty_stack_is_noop(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.exit_method_with_return("x")  # no matching enter
        assert ctx.capture_trace().is_empty


class TestLevels:
    def test_off_captures_nothing(self) -> None:
        ctx = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.OFF))
        assert ctx.enter_method(_sig("Svc", "run")) is None
        assert not ctx.is_active()
        assert ctx.capture_trace().is_empty

    def test_non_detail_suppresses_parameter_values(self) -> None:
        ctx = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.NARRATIVE))
        assert not ctx.captures_parameter_values()
        ctx.enter_method(_sig("Svc", "run", ParameterCapture("id", "secret")))
        ctx.exit_method_with_return(None)
        param = ctx.capture_trace().roots[0].signature.parameters[0]
        assert param.rendered_value == ""
        assert param.name == "id"

    def test_detail_retains_parameter_values(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig("Svc", "run", ParameterCapture("id", "42")))
        ctx.exit_method_with_return(None)
        assert ctx.capture_trace().roots[0].signature.parameters[0].rendered_value == "42"


class TestTraceId:
    def test_trace_id_is_stable(self, ctx: ContextVarNarrativeContext) -> None:
        assert ctx.trace_id() == ctx.trace_id()

    def test_trace_id_matches_captured_span(self, ctx: ContextVarNarrativeContext) -> None:
        tid = ctx.trace_id()
        ctx.enter_method(_sig("Svc", "run"))
        ctx.exit_method_with_return(None)
        span_ctx = ctx.capture_trace().roots[0].span_context
        assert span_ctx is not None
        assert span_ctx.trace_id == tid

    def test_trace_id_regenerates_after_reset(self, ctx: ContextVarNarrativeContext) -> None:
        first = ctx.trace_id()
        ctx.enter_method(_sig("Svc", "run"))
        ctx.exit_method_with_return(None)
        ctx.reset()
        assert ctx.trace_id() != first

    def test_adopt_trace_id_is_used_for_subsequent_spans(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        inbound = TraceId.generate()
        ctx.adopt_trace_id(inbound)
        assert ctx.trace_id() == inbound
        ctx.enter_method(_sig("Svc", "run"))
        ctx.exit_method_with_return(None)
        span_ctx = ctx.capture_trace().roots[0].span_context
        assert span_ctx is not None
        assert span_ctx.trace_id == inbound

    def test_adopt_trace_id_cleared_by_reset(self, ctx: ContextVarNarrativeContext) -> None:
        inbound = TraceId.generate()
        ctx.adopt_trace_id(inbound)
        ctx.reset()
        assert ctx.trace_id() != inbound


class TestStoryChapter:
    def test_story_and_chapter_derived_from_first_root(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        assert ctx.story_id() == "OrderService.placeOrder"
        assert ctx.chapter_id() == "OrderService.placeOrder"

    def test_story_id_set_once(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig("A", "first"))
        ctx.exit_method_with_return(None)
        ctx.enter_method(_sig("B", "second"))
        assert ctx.story_id() == "A.first"


class TestRequestUserMetadata:
    def test_metadata_stamped_on_spans(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.set_request_context("POST", HttpRoute.of("/orders"), ClientIp.of("203.0.113.7"))
        ctx.set_user_context(EnduserId.of("u1"), SessionId.of("s1"), TenantId.of("t1"))
        ctx.enter_method(_sig("Svc", "run"))
        ctx.exit_method_with_return(None)
        span = ctx.capture_trace().roots[0].span_context
        assert span is not None
        assert span.http_method == "POST"
        assert str(span.http_route) == "/orders"
        assert str(span.tenant_id) == "t1"
        assert str(span.enduser_id) == "u1"


class TestReset:
    def test_reset_clears_own_capture(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig("Svc", "run"))
        ctx.exit_method_with_return(None)
        ctx.reset()
        assert ctx.capture_trace().is_empty


class TestNoop:
    def test_noop_captures_nothing(self) -> None:
        assert NOOP_CONTEXT.enter_method(_sig("Svc", "run")) is None
        NOOP_CONTEXT.exit_method_with_return("x")
        assert NOOP_CONTEXT.capture_trace().is_empty
        assert not NOOP_CONTEXT.is_active()

    def test_noop_snapshot_activation_is_safe(self) -> None:
        with NOOP_CONTEXT.snapshot().activate():
            pass

    def test_noop_snapshot_opts_out_of_adoption_safely(self) -> None:
        with NOOP_CONTEXT.snapshot().activate_without_adoption():
            pass


class TestSnapshotOptOutDefault:
    def test_a_snapshot_implementing_only_activate_still_offers_the_opt_out(self) -> None:
        """The opt-out is a default, so a third-party snapshot need not know about adoption."""
        entered: list[str] = []

        class _MinimalSnapshot(ContextSnapshot):
            def activate(self) -> AbstractContextManager[None]:
                return _recording_scope(entered)

        with _MinimalSnapshot().activate_without_adoption():
            entered.append("body")

        assert entered == ["enter", "body", "exit"]


class TestConcurrencyIsolation:
    def test_threads_get_isolated_stacks(self, ctx: ContextVarNarrativeContext) -> None:
        results: dict[str, int] = {}

        def work(name: str) -> None:
            ctx.enter_method(_sig("Svc", name))
            ctx.enter_method(_sig("Svc", f"{name}_inner"))
            ctx.exit_method_with_return(None)
            ctx.exit_method_with_return(None)
            results[name] = len(ctx.capture_trace().roots)

        threads = [threading.Thread(target=work, args=(f"t{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results == {"t0": 1, "t1": 1, "t2": 1, "t3": 1}

    def test_async_tasks_get_isolated_stacks(self, ctx: ContextVarNarrativeContext) -> None:
        async def work(name: str) -> int:
            ctx.enter_method(_sig("Svc", name))
            await asyncio.sleep(0)
            ctx.enter_method(_sig("Svc", f"{name}_inner"))
            await asyncio.sleep(0)
            ctx.exit_method_with_return(None)
            ctx.exit_method_with_return(None)
            return len(ctx.capture_trace().roots)

        async def main() -> list[int]:
            return list(await asyncio.gather(work("a"), work("b"), work("c")))

        assert asyncio.run(main()) == [1, 1, 1]

    def test_reset_is_request_scoped_across_async_tasks(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        b_started = asyncio.Event()

        async def task_a() -> None:
            ctx.enter_method(_sig("Svc", "a"))
            await b_started.wait()
            ctx.reset()  # mid-flight reset must not wipe B's events

        async def task_b() -> int:
            ctx.enter_method(_sig("Svc", "b"))
            b_started.set()
            await asyncio.sleep(0.01)
            ctx.exit_method_with_return("b-done")
            return len(ctx.capture_trace().roots)

        async def main() -> int:
            _, b_roots = await asyncio.gather(task_a(), task_b())
            return b_roots

        assert asyncio.run(main()) == 1


class TestSnapshotPropagation:
    def test_snapshot_activation_shares_trace_and_parents_child(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        parent = ctx.enter_method(_sig("Svc", "parent"))
        assert parent is not None
        snap = ctx.snapshot()

        def child_work() -> None:
            ctx.enter_method(_sig("Svc", "child"))
            ctx.exit_method_with_return(None)

        thread_result: dict[str, object] = {}

        def run() -> None:
            with snap.activate():
                child_work()
                thread_result["trace"] = ctx.capture_trace()

        t = threading.Thread(target=run)
        t.start()
        t.join()
        tree = thread_result["trace"]
        assert isinstance(tree, TraceTree)
        child = tree.roots[0]
        assert child.signature.method_name == "child"
        assert child.span_context is not None
        assert child.span_context.parent_span_id == parent
