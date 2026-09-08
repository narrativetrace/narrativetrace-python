# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Coverage for scope management, deferred exits, node replay, and base defaults."""

from __future__ import annotations

from narrativetrace.context import ContextSnapshot, ContextVarNarrativeContext, NarrativeContext
from narrativetrace.events import FireAndForgetEvent, ForkCreatedEvent, MergeEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree


def _sig(cls: str, method: str) -> MethodSignature:
    return MethodSignature(cls, method, [])


class TestScope:
    def test_run_scoped_parents_under_given_span(self) -> None:
        ctx = ContextVarNarrativeContext()
        root = ctx.enter_method(_sig("Svc", "root"))
        assert root is not None
        ctx.detach_frame(root)  # simulate a detached async frame

        def scoped_work() -> None:
            ctx.enter_method(_sig("Svc", "child"))
            ctx.exit_method_with_return(None)

        ctx.run_scoped(root, scoped_work)
        ctx.exit_method_with_return(None, span_id=root)
        tree = ctx.capture_trace()
        assert tree.roots[0].signature.method_name == "root"
        assert tree.roots[0].children[0].signature.method_name == "child"

    def test_begin_and_end_scope_restore_previous(self) -> None:
        ctx = ContextVarNarrativeContext()
        a = SpanId("a" * 16)
        b = SpanId("b" * 16)
        prev = ctx.begin_scope(a)
        assert prev is None
        inner = ctx.begin_scope(b)
        assert inner == a
        ctx.end_scope(inner)
        # after restoring, scoped parent is a again — a new enter parents under a
        ctx.enter_method(_sig("Svc", "x"))
        ctx.exit_method_with_return(None, span_id=ctx.current_span_id())

    def test_current_span_id_tracks_top_of_stack(self) -> None:
        ctx = ContextVarNarrativeContext()
        assert ctx.current_span_id() is None
        span = ctx.enter_method(_sig("Svc", "run"))
        assert ctx.current_span_id() == span

    def test_capture_local_trace_matches_capture_trace(self) -> None:
        ctx = ContextVarNarrativeContext()
        ctx.enter_method(_sig("Svc", "run"))
        ctx.exit_method_with_return(None)
        assert len(ctx.capture_local_trace().roots) == len(ctx.capture_trace().roots)


class TestDeferredExit:
    def test_span_id_exit_completes_detached_frame(self) -> None:
        ctx = ContextVarNarrativeContext()
        span = ctx.enter_method(_sig("Svc", "async_call"))
        assert span is not None
        ctx.detach_frame(span)
        assert ctx.current_span_id() is None  # detached, not on active stack
        ctx.exit_method_with_return("done", span_id=span)
        node = ctx.capture_trace().roots[0]
        assert isinstance(node.outcome, Returned)
        assert node.outcome.rendered_value == "done"

    def test_exception_span_id_exit(self) -> None:
        ctx = ContextVarNarrativeContext()
        span = ctx.enter_method(_sig("Svc", "async_call"))
        assert span is not None
        ctx.detach_frame(span)
        ctx.exit_method_with_exception(ValueError("x"), "failed", span_id=span)
        assert ctx.capture_trace().roots[0].signature.error_context == "failed"


class TestConcurrencyLifecycle:
    def test_lifecycle_callbacks_emit_events(self) -> None:
        ctx = ContextVarNarrativeContext()
        ctx.on_fork_created("g1")
        ctx.on_merge("g1", [TraceNode(_sig("Svc", "m"), [], Returned("x"))])
        ctx.on_fire_and_forget_launched("g2")
        kinds = {type(e) for e in ctx._store.events()}
        assert {ForkCreatedEvent, MergeEvent, FireAndForgetEvent} <= kinds

    def test_emit_trace_node_replays_tree(self) -> None:
        ctx = ContextVarNarrativeContext()
        child = TraceNode(_sig("Svc", "child"), [], Returned("c"), duration_nanos=5)
        parent = TraceNode(_sig("Svc", "parent"), [child], Returned("p"), duration_nanos=10)
        ctx.emit_trace_node(parent, None)
        tree = ctx.capture_trace()
        assert tree.roots[0].signature.method_name == "parent"
        assert tree.roots[0].children[0].signature.method_name == "child"

    def test_a_self_referential_node_does_not_crash_replay(self) -> None:
        """Security-suite mirror (2026-09-04): unbounded recursion here hangs or crashes the
        *traced application itself*, not just an output file -- this is a public API's own input
        (any TraceNode), not a captured tree this runtime built and can trust."""
        ctx = ContextVarNarrativeContext()
        node = TraceNode(_sig("Svc", "self"), [], Returned("x"))
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        ctx.emit_trace_node(node, None)  # must not raise RecursionError
        assert ctx.capture_trace().roots[0].signature.method_name == "self"

    def test_a_ten_thousand_deep_chain_does_not_overflow_the_stack(self) -> None:
        ctx = ContextVarNarrativeContext()
        node = TraceNode(_sig("Svc", "leaf"), [], Returned("x"))
        for _ in range(10_000):
            node = TraceNode(_sig("Svc", "wrap"), [node], Returned("x"))
        ctx.emit_trace_node(node, None)  # must not raise RecursionError
        assert ctx.capture_trace().roots[0].signature.method_name == "wrap"


class TestSnapshotWrap:
    def test_wrap_activates_snapshot(self) -> None:
        ctx = ContextVarNarrativeContext()
        parent = ctx.enter_method(_sig("Svc", "parent"))
        snap = ctx.snapshot()

        def work() -> TraceTree:
            ctx.enter_method(_sig("Svc", "child"))
            ctx.exit_method_with_return(None)
            return ctx.capture_trace()

        tree = snap.wrap(work)()
        assert tree.roots[0].signature.method_name == "child"
        assert tree.roots[0].span_context is not None
        assert tree.roots[0].span_context.parent_span_id == parent


class _MinimalContext(NarrativeContext):
    """Exercises the base-class default methods (Java interface defaults)."""

    def enter_method(self, signature: MethodSignature) -> SpanId | None:
        return None

    def exit_method_with_return(self, *args: object, **kwargs: object) -> None:
        return None

    def exit_method_with_exception(self, *args: object, **kwargs: object) -> None:
        return None

    def capture_trace(self) -> TraceTree:
        return TraceTree([])

    def reset(self) -> None:
        return None

    def snapshot(self) -> ContextSnapshot:
        raise NotImplementedError


class TestBaseDefaults:
    def test_defaults(self) -> None:
        ctx = _MinimalContext()
        assert ctx.is_active() is True
        assert ctx.captures_parameter_values() is True
        assert ctx.current_span_id() is None
        assert ctx.story_id() is None
        assert ctx.chapter_id() is None
        assert isinstance(ctx.trace_id(), TraceId)
        assert ctx.capture_local_trace().is_empty
        assert ctx.begin_scope(SpanId("a" * 16)) is None
        ctx.end_scope(None)
        ctx.detach_frame(SpanId("a" * 16))
        ctx.emit_trace_node(TraceNode(_sig("S", "m"), [], None), None)
        ctx.on_fork_created("g")
        ctx.on_merge("g", [])
        ctx.on_fire_and_forget_launched("g")
        ctx.set_request_context(None, None, None)
        ctx.set_user_context(None, None, None)

    def test_run_scoped_invokes_fn(self) -> None:
        ctx = _MinimalContext()
        assert ctx.run_scoped(SpanId("a" * 16), lambda: 7) == 7
