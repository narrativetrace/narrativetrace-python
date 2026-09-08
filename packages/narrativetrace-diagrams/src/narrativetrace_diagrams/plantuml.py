# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""PlantUML sequence-diagram renderer.

``PlantUmlSequenceDiagramRenderer``: full-name participants, ``caller -> target: m()``
arrows, ``-->`` returns, ``-[#red]->`` throws labelled with the exception type, ``hnote over X :
in-flight`` for incomplete, and no ``activate``/``deactivate`` lifelines (Java parity — plan
decision point 6; ``lifelines=True`` opts into the richer form).
"""

from __future__ import annotations

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk
from narrativetrace_diagrams.text import diagram_message, identifier, quote_if_needed


def _params(node: TraceNode) -> str:
    return ", ".join(identifier(p.name) for p in node.signature.parameters)


def _return_text(value: str | None) -> str:
    return "null" if value is None else value


def _collect_participants(
    nodes: list[TraceNode], seen: dict[str, None], walk: TreeWalk | None = None
) -> None:
    walk = walk if walk is not None else TreeWalk()
    for node in nodes:
        seen.setdefault(node.signature.class_name, None)
        if walk.stop_reason(node) is None:
            walk.enter(node)
            try:
                _collect_participants(node.children, seen, walk)
            finally:
                walk.exit(node)


class PlantUmlSequenceDiagramRenderer:
    """Renders a trace tree as a PlantUML ``@startuml`` sequence diagram."""

    def __init__(self, lifelines: bool = False) -> None:
        self._lifelines = lifelines

    def render(self, tree: TraceTree) -> str:
        parts = ["@startuml\n"]
        seen: dict[str, None] = {}
        _collect_participants(tree.roots, seen)
        for participant in seen:
            parts.append(f"participant {quote_if_needed(participant)}\n")
        walk = TreeWalk()
        for root in tree.roots:
            self._render_node(root, root.signature.class_name, parts, walk)
        parts.append("@enduml")
        return "".join(parts).rstrip()

    def _render_node(self, node: TraceNode, caller: str, parts: list[str], walk: TreeWalk) -> None:
        target = node.signature.class_name
        caller_q = quote_if_needed(caller)
        target_q = quote_if_needed(target)
        method_name = identifier(node.signature.method_name)
        parts.append(f"{caller_q} -> {target_q}: {method_name}({_params(node)})\n")
        if self._lifelines:
            parts.append(f"activate {target_q}\n")
        stop_reason = walk.stop_reason(node)
        if stop_reason is None:
            walk.enter(node)
            try:
                for child in node.children:
                    self._render_node(child, target, parts, walk)
            finally:
                walk.exit(node)
        elif node.children:
            parts.append(f"hnote over {target_q} : {stop_reason}\n")
        self._render_outcome(node, caller_q, target_q, parts)

    def _render_outcome(
        self, node: TraceNode, caller_q: str, target_q: str, parts: list[str]
    ) -> None:
        outcome = node.outcome
        if isinstance(outcome, Returned):
            message = diagram_message(_return_text(outcome.rendered_value))
            parts.append(f"{target_q} --> {caller_q}: {message}\n")
            if self._lifelines:
                parts.append(f"deactivate {target_q}\n")
        elif isinstance(outcome, Threw):
            exc_type = identifier(type(outcome.exception).__name__)
            parts.append(f"{target_q} -[#red]-> {caller_q}: {exc_type}\n")
            if self._lifelines:
                parts.append(f"deactivate {target_q}\n")
        elif isinstance(outcome, Incomplete):
            parts.append(f"hnote over {target_q} : in-flight\n")
