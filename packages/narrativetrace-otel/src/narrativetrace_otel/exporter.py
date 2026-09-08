# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Batch exporter for completed NarrativeTrace trees.

``TraceSpanExporter``. Use this after capture when a full
:class:`~narrativetrace.nodes.TraceNode` forest is in hand and should be published to an OTel
backend. Parent-child structure is recreated by nesting span scopes during export; the exporter
does not reuse the original span-context ids as OTel span ids. Nodes with
:class:`~narrativetrace.outcomes.Incomplete` outcome export with ``narrative.outcome="in-flight"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.trace import Span, Tracer, use_span

from narrativetrace.tree_walk import CYCLE_MARKER, DEPTH_LIMIT_MARKER, TreeWalk
from narrativetrace_otel import attributes

if TYPE_CHECKING:
    from collections.abc import Iterable

    from narrativetrace.nodes import TraceNode

_NANOS_PER_MILLI = 1_000_000.0

_TRUNCATED_REASON = {DEPTH_LIMIT_MARKER: "depth-limit", CYCLE_MARKER: "cycle"}


class TraceSpanExporter:
    """Exports completed :class:`~narrativetrace.nodes.TraceNode` trees as nested OTel spans."""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def export(self, roots: Iterable[TraceNode]) -> None:
        """Exports each root node (and its subtree) as a span tree."""
        walk = TreeWalk()
        for root in roots:
            self._export_node(root, is_root=True, walk=walk)

    def _export_node(self, node: TraceNode, *, is_root: bool, walk: TreeWalk) -> None:
        sig = node.signature
        span = self._tracer.start_span(f"{sig.class_name}.{sig.method_name}")
        attributes.set_span_attributes(sig, span)
        attributes.set_trace_identity_attributes(node.span_context, span)
        attributes.set_nt_schema_attributes(node.span_context, span)
        span.set_attribute("narrative.duration_ms", node.duration_nanos / _NANOS_PER_MILLI)
        attributes.set_outcome_attributes(node.outcome, span)
        attributes.set_concurrency_attributes(node.concurrency, span)
        if is_root:
            attributes.set_trace_level_attributes(node.span_context, span)
        self._export_children(node, span, walk)
        span.end()

    def _export_children(self, node: TraceNode, span: Span, walk: TreeWalk) -> None:
        stop_reason = walk.stop_reason(node)
        if stop_reason is not None:
            if node.children:
                span.set_attribute("narrative.truncated", _TRUNCATED_REASON[stop_reason])
            return
        walk.enter(node)
        try:
            with use_span(span, end_on_exit=False):
                for child in node.children:
                    attributes.emit_child_event(span, child)
                    self._export_node(child, is_root=False, walk=walk)
        finally:
            walk.exit(node)
