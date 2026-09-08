# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for trace-tree pruning invariants."""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import given
from hypothesis import strategies as st

from narrativetrace.events import EnterEvent, ExitEvent, TraceEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.levels import TracingLevel
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree import build_trace_tree

TRACE = TraceId("a" * 32)


@dataclass
class _Spec:
    outcome_kind: str  # "returned" | "threw" | "incomplete"
    children: list[_Spec]


_leaf = st.builds(_Spec, st.sampled_from(["returned", "threw", "incomplete"]), st.just([]))
_spec_tree = st.recursive(
    _leaf,
    lambda children: st.builds(
        _Spec,
        st.sampled_from(["returned", "threw", "incomplete"]),
        st.lists(children, max_size=3),
    ),
    max_leaves=12,
)


class _Encoder:
    def __init__(self) -> None:
        self._counter = 0
        self.events: list[TraceEvent] = []
        self.span_ids: list[SpanId] = []

    def _next_span(self, parent: SpanId | None) -> SpanContext:
        self._counter += 1
        span = SpanId(format(self._counter, "016x"))
        self.span_ids.append(span)
        return SpanContext(trace_id=TRACE, span_id=span, parent_span_id=parent)

    def encode(self, spec: _Spec, parent: SpanId | None, clock: list[int]) -> None:
        ctx = self._next_span(parent)
        clock[0] += 1
        self.events.append(EnterEvent(ctx, clock[0], MethodSignature("C", f"m{self._counter}", [])))
        for child in spec.children:
            self.encode(child, ctx.span_id, clock)
        if spec.outcome_kind == "incomplete":
            return
        clock[0] += 1
        outcome: TraceOutcome = (
            Returned("v") if spec.outcome_kind == "returned" else Threw(ValueError())
        )
        self.events.append(ExitEvent(ctx, clock[0], outcome))


def _all_span_ids(nodes: list[TraceNode]) -> set[SpanId]:
    out: set[SpanId] = set()
    for node in nodes:
        if node.span_context is not None:
            out.add(node.span_context.span_id)
        out |= _all_span_ids(node.children)
    return out


def _error_span_ids(nodes: list[TraceNode]) -> set[SpanId]:
    out: set[SpanId] = set()
    for node in nodes:
        if isinstance(node.outcome, Threw | Incomplete) and node.span_context is not None:
            out.add(node.span_context.span_id)
        out |= _error_span_ids(node.children)
    return out


@given(_spec_tree)
def test_pruning_never_invents_nodes(spec: _Spec) -> None:
    encoder = _Encoder()
    encoder.encode(spec, None, [0])
    full = _all_span_ids(build_trace_tree(encoder.events, TracingLevel.DETAIL).roots)
    for level in (TracingLevel.ERRORS, TracingLevel.SUMMARY, TracingLevel.NARRATIVE):
        pruned = _all_span_ids(build_trace_tree(encoder.events, level).roots)
        assert pruned <= full


@given(_spec_tree)
def test_every_error_node_survives_errors_level(spec: _Spec) -> None:
    encoder = _Encoder()
    encoder.encode(spec, None, [0])
    detail_roots = build_trace_tree(encoder.events, TracingLevel.DETAIL).roots
    errors_roots = build_trace_tree(encoder.events, TracingLevel.ERRORS).roots
    assert _error_span_ids(detail_roots) <= _all_span_ids(errors_roots)
