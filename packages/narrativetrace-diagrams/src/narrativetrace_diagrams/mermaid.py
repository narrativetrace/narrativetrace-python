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

``MermaidSequenceDiagramRenderer`` and ``PlantUmlSequenceDiagramRenderer`` (:mod:`plantuml`) share
one traversal (:mod:`sequence_walk`); ``MermaidSequenceGrammar`` here is the Mermaid-specific
literals that traversal composes with -- see :mod:`sequence_grammar` for the hook contract.
"""

from __future__ import annotations

from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk
from narrativetrace_diagrams.diagram_label import DiagramLabel
from narrativetrace_diagrams.sequence_grammar import LimitReason
from narrativetrace_diagrams.sequence_walk import collect_participants, render_sequence


class MermaidSequenceGrammar:
    """Mermaid ``sequenceDiagram`` grammar: ``->>`` call arrows, ``-->>`` returns, ``-x`` throws,
    ``Note over`` for an in-flight outcome or a walk limit.

    Stateless -- Mermaid's alias mode is a difference in the label-mapping function
    ``MermaidSequenceDiagramRenderer`` passes to :func:`sequence_walk.render_sequence`, not in
    this grammar, so one instance serves both ``render`` and ``render_with_aliases``. Mermaid has
    no lifeline notion, so ``activate``/``deactivate`` are no-ops.
    """

    def header(self) -> str:
        return "sequenceDiagram\n"

    def participant(self, label: DiagramLabel) -> str:
        return f"    participant {label.text}\n"

    def call_arrow(
        self, caller: DiagramLabel, target: DiagramLabel, signature: DiagramLabel
    ) -> str:
        return f"    {caller.text}->>{target.text}: {signature.text}\n"

    def activate(self, target: DiagramLabel) -> str:
        return ""

    def return_arrow(
        self, target: DiagramLabel, caller: DiagramLabel, message: DiagramLabel
    ) -> str:
        return f"    {target.text}-->>{caller.text}: {message.text}\n"

    def throw_arrow(
        self, target: DiagramLabel, caller: DiagramLabel, exception_type: DiagramLabel
    ) -> str:
        return f"    {target.text}-x{caller.text}: {exception_type.text}\n"

    def deactivate(self, target: DiagramLabel) -> str:
        return ""

    def incomplete(self, target: DiagramLabel) -> str:
        return f"    Note over {target.text}: in-flight\n"

    def limited_note(self, target: DiagramLabel, reason: LimitReason) -> str:
        return f"    Note over {target.text}: {reason}\n"

    def footer(self) -> str:
        return ""


def _extract_upper(name: str) -> str:
    capitals = [c for c in name if c.isupper()]
    return "".join(capitals[:2]) if len(capitals) >= 2 else "".join(capitals)


def _build_aliases(participants: list[str]) -> dict[str, DiagramLabel]:
    aliases: dict[str, DiagramLabel] = {}
    used: set[str] = set()
    for name in participants:
        alias = _extract_upper(name)
        if not alias:
            # No uppercase letters to extract from: fall back to a grammar-safe token derived
            # from the whole name, never the raw name itself -- a raw fallback put an
            # unsanitized class name in bare-token position on every arrow line (structural
            # breakage, e.g. a "->>" or ":" in the name; collisions after sanitization, e.g.
            # `a"b` and `a'b` both reducing to `ab`, went undetected because the pre-sanitized
            # strings looked distinct here).
            alias = DiagramLabel.alias(name).text
        if alias in used:
            suffix = 2
            while f"{alias}{suffix}" in used:
                suffix += 1
            alias = f"{alias}{suffix}"
        used.add(alias)
        aliases[name] = DiagramLabel.identifier(alias)
    return aliases


class MermaidSequenceDiagramRenderer:
    """Renders a trace tree as a Mermaid ``sequenceDiagram``."""

    _GRAMMAR = MermaidSequenceGrammar()

    def render(self, tree: TraceTree) -> str:
        """Renders with full class names as participants."""
        grammar = self._GRAMMAR
        parts = [grammar.header()]
        for participant in collect_participants(tree.roots):
            parts.append(grammar.participant(DiagramLabel.plain_token(participant)))
        walk = TreeWalk()
        for root in tree.roots:
            render_sequence(root, grammar, DiagramLabel.plain_token, parts, walk)
        parts.append(grammar.footer())
        return "".join(parts).rstrip()

    def render_with_aliases(self, tree: TraceTree) -> str:
        """Renders with short derived aliases (``participant OS as "OrderService"``)."""
        grammar = self._GRAMMAR
        parts = [grammar.header()]
        participants = collect_participants(tree.roots)
        aliases = _build_aliases(participants)
        for participant in participants:
            alias_label = aliases[participant]
            display_label = DiagramLabel.quoted_identifier(participant)
            parts.append(grammar.participant(alias_label.aliased_as(display_label)))
        walk = TreeWalk()
        for root in tree.roots:
            render_sequence(root, grammar, aliases.__getitem__, parts, walk)
        parts.append(grammar.footer())
        return "".join(parts).rstrip()
