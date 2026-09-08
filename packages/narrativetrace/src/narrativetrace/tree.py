# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Builds immutable trace trees from append-only events, applying level pruning.

``TraceTree`` / ``DefaultTraceTree`` / ``TraceTreeBuilder``. This is the translation
layer between the event model used during capture and the tree model used for rendering and
export.

Tree pruning (``ERRORS`` and ``SUMMARY``) happens here; parameter suppression happens earlier
during capture, so ``DETAIL`` parameter values cannot be recovered from ``NARRATIVE``-or-below
events.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from narrativetrace.events import EnterEvent, ExitEvent, TraceEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.levels import TracingLevel
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Threw, TraceOutcome
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree_walk import MAX_DEPTH, TreeWalk


@dataclass(frozen=True, slots=True)
class TraceTree:
    """Immutable tree of root :class:`TraceNode`s returned by capture APIs.

    ``trace_id`` is the tree's own identity, resolved once at construction — *adopt* the id the
    capturing context assigned, else *inherit* the first span context found anywhere in the tree,
    else *generate* a fresh W3C id. It lives here rather than in an exporter deliberately: two
    exporters reading one tree must be unable to name two different traces.

    An empty tree carries no identity (``trace_id is None``): nothing ran, so there is nothing to
    identify, and an assigned id is dropped rather than naming an empty capture.
    """

    roots: list[TraceNode] = field(default_factory=list)
    trace_id: TraceId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", self._resolved_trace_id())

    def _resolved_trace_id(self) -> TraceId | None:
        if not self.roots:
            return None
        if self.trace_id is not None:
            return self.trace_id
        inherited = self.inherited_span_context
        return inherited.trace_id if inherited is not None else TraceId.generate()

    @property
    def is_empty(self) -> bool:
        """Whether this tree contains no traced nodes."""
        return len(self.roots) == 0

    @property
    def inherited_span_context(self) -> SpanContext | None:
        """First span context anywhere in the tree, depth-first, or ``None`` if none exists.

        One tree is one trace, so a real context found at any depth answers for every node —
        a mixed tree whose only span sits under a context-free root still correlates.
        """
        return _first_span_context(self.roots)


def _first_span_context(nodes: list[TraceNode], walk: TreeWalk | None = None) -> SpanContext | None:
    walk = walk if walk is not None else TreeWalk()
    for node in nodes:
        if node.span_context is not None:
            return node.span_context
        if walk.stop_reason(node) is not None:
            continue  # a cyclic or pathologically deep subtree contributes no span context
        walk.enter(node)
        try:
            from_child = _first_span_context(node.children, walk)
        finally:
            walk.exit(node)
        if from_child is not None:
            return from_child
    return None


@dataclass(frozen=True, slots=True)
class _EventIndex:
    enters: dict[SpanId, EnterEvent]
    exits: dict[SpanId, ExitEvent]
    child_span_ids: dict[SpanId, list[SpanId]]
    root_span_ids: list[SpanId]

    @classmethod
    def of(cls, events: list[TraceEvent]) -> _EventIndex:
        enters: dict[SpanId, EnterEvent] = {}
        exits: dict[SpanId, ExitEvent] = {}
        for event in events:
            if isinstance(event, EnterEvent):
                enters[event.span_context.span_id] = event
            elif isinstance(event, ExitEvent):
                exits[event.span_context.span_id] = event
        child_span_ids: dict[SpanId, list[SpanId]] = {}
        root_span_ids: list[SpanId] = []
        for event in events:
            if not isinstance(event, EnterEvent):
                continue
            span_id = event.span_context.span_id
            parent = event.span_context.parent_span_id
            if parent is None or parent not in enters:
                root_span_ids.append(span_id)
            else:
                child_span_ids.setdefault(parent, []).append(span_id)
        return cls(enters, exits, child_span_ids, root_span_ids)


def build_trace_tree(
    events: list[TraceEvent], level: TracingLevel, trace_id: TraceId | None = None
) -> TraceTree:
    """Reconstructs an immutable :class:`TraceTree` from events, pruned to ``level``.

    Args:
        events: The append-only event stream to reassemble.
        level: Pruning level; ``OFF`` yields an empty (and therefore identity-free) tree.
        trace_id: The id the capturing context already assigned to this trace, if any. Passed
            straight through — the builder never generates, so a context that stayed idle does
            not acquire an identity merely by being captured.
    """
    if level is TracingLevel.OFF:
        return TraceTree([])

    index = _EventIndex.of(events)
    roots = [_build_node(span_id, index) for span_id in index.root_span_ids]

    if level is TracingLevel.ERRORS:
        roots = _retain_error_paths(roots)
    elif level is TracingLevel.SUMMARY:
        roots = _prune_summary(roots)

    return TraceTree(roots, trace_id)


def _build_node(
    span_id: SpanId,
    index: _EventIndex,
    *,
    depth: int = 0,
    ancestors: frozenset[SpanId] = frozenset(),
) -> TraceNode:
    enter = index.enters[span_id]
    exit_event = index.exits.get(span_id)
    children = _build_children(span_id, index, depth, ancestors)

    outcome: TraceOutcome = exit_event.outcome if exit_event is not None else Incomplete()
    duration = exit_event.timestamp_nanos - enter.timestamp_nanos if exit_event is not None else 0
    signature = _apply_error_context(enter.signature, exit_event)
    return TraceNode(
        signature=signature,
        children=children,
        outcome=outcome,
        duration_nanos=duration,
        start_time_nanos=enter.timestamp_nanos,
        concurrency=enter.concurrency,
        span_context=enter.span_context,
        thread=enter.thread,
    )


def _build_children(
    span_id: SpanId, index: _EventIndex, depth: int, ancestors: frozenset[SpanId]
) -> list[TraceNode]:
    """The children of ``span_id``, or none once the walk is too deep or ``span_id`` is already
    its own ancestor -- a replayed/malformed event stream can reuse an ancestor's span id as a
    descendant's, forming a genuine cycle in ``child_span_ids`` that a fixed, well-formed capture
    can never produce. Tracked by span id (a value, not yet a built ``TraceNode``) rather than
    :class:`~narrativetrace.tree_walk.TreeWalk`'s object identity, since the nodes being guarded
    against don't exist until this call returns.
    """
    if span_id in ancestors or depth >= MAX_DEPTH:
        return []
    child_ancestors = ancestors | {span_id}
    return [
        _build_node(child_id, index, depth=depth + 1, ancestors=child_ancestors)
        for child_id in index.child_span_ids.get(span_id, [])
    ]


def _apply_error_context(sig: MethodSignature, exit_event: ExitEvent | None) -> MethodSignature:
    """Attaches a resolved ``@on_error`` template, leaving every other captured field alone.

    ``replace`` rather than a positional rebuild: the signature carries identity fields the tree
    never looks at (package, return type, raw narration template), and rebuilding by hand silently
    dropped whichever ones were added last.
    """
    if exit_event is None or exit_event.error_context is None:
        return sig
    return replace(sig, error_context=exit_event.error_context)


def _is_error_outcome(node: TraceNode) -> bool:
    return isinstance(node.outcome, Threw | Incomplete)


def _rebuilt(node: TraceNode, children: list[TraceNode]) -> TraceNode:
    """Copies a node with a different child list; pruning must not drop any other captured field."""
    return replace(node, children=children)


def _retain_error_paths(nodes: list[TraceNode]) -> list[TraceNode]:
    result = []
    for node in nodes:
        pruned = _retain_error_paths_node(node)
        if pruned is not None:
            result.append(pruned)
    return result


def _retain_error_paths_node(node: TraceNode) -> TraceNode | None:
    if _is_error_outcome(node):
        return node
    error_children = _retain_error_paths(node.children)
    if not error_children:
        return None
    return _rebuilt(node, error_children)


def _prune_summary(roots: list[TraceNode]) -> list[TraceNode]:
    return [_prune_summary_node(root, is_root=True) for root in roots]


def _prune_summary_node(node: TraceNode, *, is_root: bool) -> TraceNode:
    if not node.children or is_root:
        collected: list[TraceNode] = []
        for child in node.children:
            _prune_summary_collect(child, collected)
        return _rebuilt(node, collected)
    return node


def _prune_summary_collect(node: TraceNode, collector: list[TraceNode]) -> None:
    if not node.children or _is_error_outcome(node):
        collector.append(node)
    else:
        for child in node.children:
            _prune_summary_collect(child, collector)
