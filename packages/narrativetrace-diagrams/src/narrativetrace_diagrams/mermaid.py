# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Mermaid sequence-diagram renderer.

``MermaidSequenceDiagramRenderer``. Root entry points render as self-call/self-return
arrows; returns use ``-->>``; throws use ``-x`` labelled with the exception type name; incomplete
outcomes render as ``Note over X: in-flight`` (no return arrow). ``render_with_aliases`` derives
short participant aliases (≥2 capitals → first two; single capital → that letter; all-lowercase →
full name; conflicts → ``OS``/``OS2``/``OS3``).
"""

from __future__ import annotations

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
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


def _extract_upper(name: str) -> str:
    capitals = [c for c in name if c.isupper()]
    return "".join(capitals[:2]) if len(capitals) >= 2 else "".join(capitals)


def _build_aliases(participants: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    used: set[str] = set()
    for name in participants:
        alias = _extract_upper(name) or name
        if alias in used:
            suffix = 2
            while f"{alias}{suffix}" in used:
                suffix += 1
            alias = f"{alias}{suffix}"
        used.add(alias)
        aliases[name] = alias
    return aliases


class MermaidSequenceDiagramRenderer:
    """Renders a trace tree as a Mermaid ``sequenceDiagram``."""

    def render(self, tree: TraceTree) -> str:
        """Renders with full class names as participants."""
        return self._render(tree, aliases=None)

    def render_with_aliases(self, tree: TraceTree) -> str:
        """Renders with short derived aliases (``participant OS as "OrderService"``)."""
        seen: dict[str, None] = {}
        _collect_participants(tree.roots, seen)
        return self._render(tree, aliases=_build_aliases(list(seen)))

    def _render(self, tree: TraceTree, aliases: dict[str, str] | None) -> str:
        parts = ["sequenceDiagram\n"]
        seen: dict[str, None] = {}
        _collect_participants(tree.roots, seen)
        for participant in seen:
            if aliases is None:
                parts.append(f"    participant {quote_if_needed(participant)}\n")
            else:
                parts.append(
                    f"    participant {aliases[participant]} as {quote_if_needed(participant)}\n"
                )
        walk = TreeWalk()
        for root in tree.roots:
            self._render_node(root, root.signature.class_name, aliases, parts, walk)
        return "".join(parts).rstrip()

    def _label(self, name: str, aliases: dict[str, str] | None) -> str:
        return quote_if_needed(name) if aliases is None else aliases[name]

    def _render_node(
        self,
        node: TraceNode,
        caller: str,
        aliases: dict[str, str] | None,
        parts: list[str],
        walk: TreeWalk,
    ) -> None:
        target = node.signature.class_name
        caller_label = self._label(caller, aliases)
        target_label = self._label(target, aliases)
        method_name = identifier(node.signature.method_name)
        parts.append(f"    {caller_label}->>{target_label}: {method_name}({_params(node)})\n")
        self._render_children_or_marker(node, target, aliases, parts, walk, target_label)
        self._render_outcome(node.outcome, caller_label, target_label, parts)

    def _render_children_or_marker(
        self,
        node: TraceNode,
        target: str,
        aliases: dict[str, str] | None,
        parts: list[str],
        walk: TreeWalk,
        target_label: str,
    ) -> None:
        stop_reason = walk.stop_reason(node)
        if stop_reason is None:
            walk.enter(node)
            try:
                for child in node.children:
                    self._render_node(child, target, aliases, parts, walk)
            finally:
                walk.exit(node)
        elif node.children:
            parts.append(f"    Note over {target_label}: {stop_reason}\n")

    def _render_outcome(
        self, outcome: TraceOutcome | None, caller_label: str, target_label: str, parts: list[str]
    ) -> None:
        if isinstance(outcome, Returned):
            message = diagram_message(_return_text(outcome.rendered_value))
            parts.append(f"    {target_label}-->>{caller_label}: {message}\n")
        elif isinstance(outcome, Threw):
            exc_type = identifier(type(outcome.exception).__name__)
            parts.append(f"    {target_label}-x{caller_label}: {exc_type}\n")
        elif isinstance(outcome, Incomplete):
            parts.append(f"    Note over {target_label}: in-flight\n")
