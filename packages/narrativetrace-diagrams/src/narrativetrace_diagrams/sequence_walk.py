# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one traversal both sequence-diagram renderers share: bounded, cycle-safe, emitting exactly
one call arrow on the way into a node and exactly one outcome (return, throw, or in-flight note)
on the way out -- :class:`~narrativetrace.tree_walk.TreeWalk`'s enter/exit/stop_reason shape
matches this exactly.

INTENT: ``MermaidSequenceDiagramRenderer`` and ``PlantUmlSequenceDiagramRenderer`` used to each
own a private copy of participant collection and this enter/recurse/outcome walk, differing only
in the grammar (arrow syntax, note wording) and the label-mapping function each closed over.
Extracted by composition, not inheritance: this module owns the walk and participant collection
-- written once -- a :class:`~narrativetrace_diagrams.sequence_grammar.SequenceGrammar` owns
everything the two formats disagree about, and the caller-supplied ``participant_label`` function
owns how a raw class name becomes the
:class:`~narrativetrace_diagrams.diagram_label.DiagramLabel` an arrow names
(identity/quoted for both formats' plain mode, an alias lookup for Mermaid's alias mode) --
deliberately a parameter here, never a grammar hook, per ``DiagramLabel``'s own invariant that a
raw trace string never reaches a grammar.

A node beyond :data:`~narrativetrace.tree_walk.MAX_DEPTH` or already on the current path still
gets its own call arrow and outcome, rendered exactly like a leaf -- the walk simply never
descends into its children. When such a node still has children being truncated, the grammar's
``limited_note`` is appended too; a node whose own subtree is empty (e.g. a childless leaf that
happens to be reported as an ancestor) is not, since nothing was truncated for it. This is the
behavior every existing renderer test, and ``SequenceWalkContractTest``, pin for both grammars at
once.
"""

from __future__ import annotations

from collections.abc import Callable

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw
from narrativetrace.tree_walk import TreeWalk
from narrativetrace_diagrams.diagram_label import DiagramLabel
from narrativetrace_diagrams.sequence_grammar import LimitReason, SequenceGrammar

ParticipantLabel = Callable[[str], DiagramLabel]
"""How a raw class name becomes the label an arrow names."""


def collect_participants(nodes: list[TraceNode]) -> list[str]:
    """The participant lane-up of a sequence diagram: every class the trace touched, reachable
    from ``nodes``, in first-appearance order.

    The walk is bounded exactly as it is during rendering, so a cyclic or pathologically deep
    tree cannot make this diverge from :func:`render_sequence`'s own traversal. A node the walk
    stops at still contributes its lane -- the renderers do emit an arrow for it.
    """
    seen: dict[str, None] = {}
    _collect(nodes, seen, TreeWalk())
    return list(seen)


def _collect(nodes: list[TraceNode], seen: dict[str, None], walk: TreeWalk) -> None:
    for node in nodes:
        seen.setdefault(node.signature.class_name, None)
        if walk.stop_reason(node) is None:
            walk.enter(node)
            try:
                _collect(node.children, seen, walk)
            finally:
                walk.exit(node)


def render_sequence(
    root: TraceNode,
    grammar: SequenceGrammar,
    participant_label: ParticipantLabel,
    parts: list[str],
    walk: TreeWalk,
) -> None:
    """Walks ``root``, appending every arrow and note ``grammar`` produces to ``parts``.

    ``walk`` is owned by the caller so a multi-root tree can share one traversal's ancestry
    across its roots, exactly as the renderers already did before this was extracted.
    """
    _render_node(root, root.signature.class_name, grammar, participant_label, parts, walk)


def _return_text(value: str | None) -> str:
    return "null" if value is None else value


def _render_node(
    node: TraceNode,
    caller: str,
    grammar: SequenceGrammar,
    participant_label: ParticipantLabel,
    parts: list[str],
    walk: TreeWalk,
) -> None:
    target = node.signature.class_name
    _append_call_arrow(node, caller, target, grammar, participant_label, parts)
    _render_children_or_marker(node, target, grammar, participant_label, parts, walk)
    _append_outcome(node, caller, target, grammar, participant_label, parts)


def _render_children_or_marker(
    node: TraceNode,
    target: str,
    grammar: SequenceGrammar,
    participant_label: ParticipantLabel,
    parts: list[str],
    walk: TreeWalk,
) -> None:
    stop_reason = walk.stop_reason(node)
    if stop_reason is None:
        walk.enter(node)
        try:
            for child in node.children:
                _render_node(child, target, grammar, participant_label, parts, walk)
        finally:
            walk.exit(node)
    elif node.children:
        parts.append(grammar.limited_note(participant_label(target), LimitReason(stop_reason)))


def _append_call_arrow(
    node: TraceNode,
    caller: str,
    target: str,
    grammar: SequenceGrammar,
    participant_label: ParticipantLabel,
    parts: list[str],
) -> None:
    method = DiagramLabel.identifier(node.signature.method_name)
    params = [DiagramLabel.identifier(p.name) for p in node.signature.parameters]
    signature = method.with_parameters(params)
    target_label = participant_label(target)
    parts.append(grammar.call_arrow(participant_label(caller), target_label, signature))
    parts.append(grammar.activate(target_label))


def _append_outcome(
    node: TraceNode,
    caller: str,
    target: str,
    grammar: SequenceGrammar,
    participant_label: ParticipantLabel,
    parts: list[str],
) -> None:
    outcome = node.outcome
    target_label = participant_label(target)
    caller_label = participant_label(caller)
    if isinstance(outcome, Returned):
        message = DiagramLabel.message(_return_text(outcome.rendered_value))
        parts.append(grammar.return_arrow(target_label, caller_label, message))
        parts.append(grammar.deactivate(target_label))
    elif isinstance(outcome, Threw):
        exception_type = DiagramLabel.identifier(type(outcome.exception).__name__)
        parts.append(grammar.throw_arrow(target_label, caller_label, exception_type))
        parts.append(grammar.deactivate(target_label))
    elif isinstance(outcome, Incomplete):
        parts.append(grammar.incomplete(target_label))
