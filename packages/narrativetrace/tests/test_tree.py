# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for trace-tree building and level pruning (``TraceTreeBuilder``)."""

from __future__ import annotations

from narrativetrace.events import EnterEvent, ExitEvent, TraceEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.levels import TracingLevel
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree, build_trace_tree

TRACE = TraceId("a" * 32)


def _span(hex_char: str, parent: SpanId | None = None) -> SpanContext:
    return SpanContext(trace_id=TRACE, span_id=SpanId(hex_char * 16), parent_span_id=parent)


def _node(**kw: object) -> TraceNode:
    fields: dict[str, object] = {"signature": MethodSignature("C", "m", []), "children": []}
    fields.update(kw)
    return TraceNode(**fields)  # type: ignore[arg-type]


def _enter(ctx: SpanContext, name: str, ts: int) -> EnterEvent:
    return EnterEvent(ctx, ts, MethodSignature("C", name, []))


def _exit(ctx: SpanContext, ts: int, outcome: TraceOutcome) -> ExitEvent:
    return ExitEvent(ctx, ts, outcome)


class TestBasicBuild:
    def test_builds_parent_child_with_duration_and_outcome(self) -> None:
        root, child = _span("a"), _span("b", parent=SpanId("a" * 16))
        events: list[TraceEvent] = [
            _enter(root, "root", 0),
            _enter(child, "child", 10),
            _exit(child, 30, Returned("c")),
            _exit(root, 100, Returned("r")),
        ]
        tree = build_trace_tree(events, TracingLevel.DETAIL)
        assert len(tree.roots) == 1
        node = tree.roots[0]
        assert node.signature.method_name == "root"
        assert node.duration_nanos == 100
        assert isinstance(node.outcome, Returned)
        assert node.children[0].signature.method_name == "child"
        assert node.children[0].duration_nanos == 20

    def test_pending_enter_is_incomplete(self) -> None:
        root = _span("a")
        tree = build_trace_tree([_enter(root, "root", 0)], TracingLevel.DETAIL)
        assert isinstance(tree.roots[0].outcome, Incomplete)

    def test_a_pending_enter_reports_no_duration_rather_than_a_guess(self) -> None:
        """Nothing measured a span that never exited, so its duration is zero, not elapsed time."""
        tree = build_trace_tree([_enter(_span("a"), "root", 7)], TracingLevel.DETAIL)
        assert tree.roots[0].duration_nanos == 0

    def test_a_node_starts_when_its_enter_event_was_recorded(self) -> None:
        """`start_time_nanos` anchors every exported timestamp, so it must be the enter's own."""
        root = _span("a")
        events: list[TraceEvent] = [_enter(root, "root", 1234), _exit(root, 1334, Returned("r"))]

        tree = build_trace_tree(events, TracingLevel.DETAIL)

        assert tree.roots[0].start_time_nanos == 1234
        assert tree.roots[0].duration_nanos == 100

    def test_orphan_parent_promotes_child_to_root(self) -> None:
        child = _span("b", parent=SpanId("f" * 16))  # parent never entered
        tree = build_trace_tree([_enter(child, "child", 0)], TracingLevel.DETAIL)
        assert len(tree.roots) == 1
        assert tree.roots[0].signature.method_name == "child"

    def test_exit_error_context_applied_to_signature(self) -> None:
        root = _span("a")
        events: list[TraceEvent] = [
            _enter(root, "root", 0),
            ExitEvent(root, 10, Threw(ValueError("x")), error_context="failed to root"),
        ]
        tree = build_trace_tree(events, TracingLevel.DETAIL)
        assert tree.roots[0].signature.error_context == "failed to root"


class TestOff:
    def test_off_yields_empty_tree(self) -> None:
        root = _span("a")
        events: list[TraceEvent] = [_enter(root, "root", 0), _exit(root, 10, Returned("r"))]
        tree = build_trace_tree(events, TracingLevel.OFF)
        assert tree.is_empty
        assert tree.roots == []


def _chain_depth(node: TraceNode) -> int:
    return 1 + max((_chain_depth(c) for c in node.children), default=0)


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): TraceNode.children is a plain mutable list even under
    frozen=True, so a hand-built or replayed tree can be genuinely cyclic, and a deep tree (a
    recursive business method, or a crafted event stream) is ordinary. Every walk here used
    unbounded native recursion with no depth bound or cycle guard -- both crashed with an uncaught
    RecursionError."""

    def test_a_self_referential_node_does_not_crash_span_context_inheritance(self) -> None:
        node = _node()
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        tree = TraceTree([node])
        assert tree.inherited_span_context is None

    def test_a_ten_thousand_deep_hand_built_chain_does_not_overflow_the_stack(self) -> None:
        node = _node()
        for _ in range(10_000):
            node = _node(children=[node])
        tree = TraceTree([node])  # __post_init__ walks the chain looking for a span context
        assert tree.inherited_span_context is None

    def test_a_crafted_cyclic_event_stream_does_not_crash_the_builder(self) -> None:
        """A span id can legitimately reappear in a replayed/malformed event stream; if the
        replay reuses an ancestor's span id as a descendant's, ``child_span_ids`` forms a genuine
        cycle the builder must not recurse into forever."""
        root_ctx = _span("a")
        child_ctx = _span("b", parent=root_ctx.span_id)
        duplicate_root_ctx = _span("a", parent=child_ctx.span_id)
        events: list[TraceEvent] = [
            _enter(root_ctx, "root", 0),
            _enter(child_ctx, "child", 1),
            _enter(duplicate_root_ctx, "root-again", 2),
        ]
        tree = build_trace_tree(events, TracingLevel.DETAIL)
        assert tree.roots != []

    def test_a_ten_thousand_deep_event_chain_is_truncated_not_crashed(self) -> None:
        events: list[TraceEvent] = []
        parent: SpanId | None = None
        for i in range(10_000):
            ctx = SpanContext(trace_id=TRACE, span_id=SpanId(f"{i:016x}"), parent_span_id=parent)
            events.append(_enter(ctx, f"m{i}", i))
            parent = ctx.span_id
        tree = build_trace_tree(events, TracingLevel.DETAIL)
        assert 1 < _chain_depth(tree.roots[0]) < 1000


def _tree_events(chain: list[tuple[str, str, TraceOutcome]]) -> list[TraceEvent]:
    """Builds a linear parent→child chain of (hex_char, name, outcome), timestamps by depth."""
    events: list[TraceEvent] = []
    parent: SpanId | None = None
    ctxs: list[SpanContext] = []
    for depth, (hex_char, name, _outcome) in enumerate(chain):
        ctx = _span(hex_char, parent=parent)
        ctxs.append(ctx)
        events.append(_enter(ctx, name, depth * 10))
        parent = ctx.span_id
    for depth in reversed(range(len(chain))):
        events.append(_exit(ctxs[depth], 1000 - depth, chain[depth][2]))
    return events


def _names(nodes: list[TraceNode]) -> set[str]:
    out: set[str] = set()
    for node in nodes:
        out.add(node.signature.method_name)
        out |= _names(node.children)
    return out


class TestErrorsPruning:
    def test_returned_root_with_throwing_child_retains_error_path(self) -> None:
        root, child = _span("a"), _span("b", parent=SpanId("a" * 16))
        events: list[TraceEvent] = [
            _enter(root, "root", 0),
            _enter(child, "child", 10),
            _exit(child, 20, Threw(ValueError())),
            _exit(root, 100, Returned("r")),
        ]
        tree = build_trace_tree(events, TracingLevel.ERRORS)
        assert _names(tree.roots) == {"root", "child"}

    def test_pure_success_branch_dropped(self) -> None:
        root, ok = _span("a"), _span("b", parent=SpanId("a" * 16))
        events: list[TraceEvent] = [
            _enter(root, "root", 0),
            _enter(ok, "ok", 10),
            _exit(ok, 20, Returned("ok")),
            _exit(root, 100, Returned("r")),
        ]
        assert build_trace_tree(events, TracingLevel.ERRORS).roots == []

    def test_error_root_keeps_successful_descendants(self) -> None:
        root, ok = _span("a"), _span("b", parent=SpanId("a" * 16))
        events: list[TraceEvent] = [
            _enter(root, "root", 0),
            _enter(ok, "ok", 10),
            _exit(ok, 20, Returned("ok")),
            _exit(root, 100, Threw(ValueError())),
        ]
        tree = build_trace_tree(events, TracingLevel.ERRORS)
        assert _names(tree.roots) == {"root", "ok"}


class TestSummaryPruning:
    def test_intermediate_success_frame_collapsed_to_root_and_leaf(self) -> None:
        chain: list[tuple[str, str, TraceOutcome]] = [
            ("a", "root", Returned("r")),
            ("b", "middle", Returned("m")),
            ("c", "leaf", Returned("l")),
        ]
        tree = build_trace_tree(_tree_events(chain), TracingLevel.SUMMARY)
        assert _names(tree.roots) == {"root", "leaf"}

    def test_intermediate_error_frame_retained(self) -> None:
        chain: list[tuple[str, str, TraceOutcome]] = [
            ("a", "root", Returned("r")),
            ("b", "middle", Threw(ValueError())),
            ("c", "leaf", Returned("l")),
        ]
        tree = build_trace_tree(_tree_events(chain), TracingLevel.SUMMARY)
        assert "middle" in _names(tree.roots)

    def test_summary_differs_from_narrative_for_success_chain(self) -> None:
        chain: list[tuple[str, str, TraceOutcome]] = [
            ("a", "root", Returned("r")),
            ("b", "middle", Returned("m")),
            ("c", "leaf", Returned("l")),
        ]
        events = _tree_events(chain)
        summary = _names(build_trace_tree(events, TracingLevel.SUMMARY).roots)
        narrative = _names(build_trace_tree(events, TracingLevel.NARRATIVE).roots)
        assert summary != narrative
        assert "middle" in narrative and "middle" not in summary


class TestTreeIdentity:
    """One tree is one trace, so the tree — not any exporter — owns the trace id."""

    def test_a_populated_tree_built_by_hand_generates_a_real_trace_id(self) -> None:
        tree = TraceTree([_node()])

        assert tree.trace_id is not None
        assert tree.trace_id != TraceId("0" * 32)

    def test_an_empty_tree_has_no_identity_because_nothing_ran(self) -> None:
        assert TraceTree([]).trace_id is None

    def test_two_independently_built_trees_never_share_a_generated_trace_id(self) -> None:
        assert TraceTree([_node()]).trace_id != TraceTree([_node()]).trace_id

    def test_a_generated_trace_id_is_stable_for_the_life_of_the_tree(self) -> None:
        tree = TraceTree([_node()])

        assert tree.trace_id == tree.trace_id

    def test_an_assigned_trace_id_is_adopted_rather_than_generated(self) -> None:
        assert TraceTree([_node()], TRACE).trace_id == TRACE

    def test_a_span_context_anywhere_in_the_tree_is_inherited_before_generating(self) -> None:
        deep = _node(span_context=_span("b"))
        tree = TraceTree([_node(children=[_node(children=[deep])])])

        assert tree.trace_id == TRACE

    def test_an_assigned_id_beats_inheritance_because_the_capturing_context_ruled(self) -> None:
        assigned = TraceId("c" * 32)
        tree = TraceTree([_node(span_context=_span("b"))], assigned)

        assert tree.trace_id == assigned

    def test_an_empty_tree_keeps_no_identity_even_when_one_is_assigned(self) -> None:
        assert TraceTree([], TRACE).trace_id is None

    def test_the_inherited_span_context_is_the_first_one_found_depth_first(self) -> None:
        deep = _node(span_context=_span("b"))
        shallow_sibling = _node(span_context=_span("c"))
        tree = TraceTree([_node(children=[deep]), shallow_sibling])

        assert tree.inherited_span_context is not None
        assert tree.inherited_span_context.span_id == SpanId("b" * 16)

    def test_a_tree_without_any_span_context_inherits_nothing(self) -> None:
        assert TraceTree([_node()]).inherited_span_context is None


class TestBuilderIdentity:
    def test_the_builder_passes_the_context_assigned_id_through_untouched(self) -> None:
        events: list[TraceEvent] = [_enter(_span("a"), "root", 0)]
        assigned = TraceId("c" * 32)

        assert build_trace_tree(events, TracingLevel.DETAIL, assigned).trace_id == assigned

    def test_the_builder_inherits_from_the_events_when_given_no_id(self) -> None:
        events: list[TraceEvent] = [_enter(_span("a"), "root", 0)]

        assert build_trace_tree(events, TracingLevel.DETAIL).trace_id == TRACE

    def test_a_pruned_away_tree_carries_no_identity(self) -> None:
        events: list[TraceEvent] = [_enter(_span("a"), "root", 0)]

        assert build_trace_tree(events, TracingLevel.OFF, TRACE).trace_id is None
