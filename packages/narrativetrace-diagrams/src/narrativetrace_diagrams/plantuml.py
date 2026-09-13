# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""PlantUML sequence-diagram renderer.

``PlantUmlSequenceDiagramRenderer``: full-name participants, ``caller -> target: m()``
arrows, ``-->`` returns, ``-[#red]->`` throws labelled with the exception type, ``hnote over X :
in-flight`` for incomplete, and no ``activate``/``deactivate`` lifelines (Java parity -- plan
decision point 6; ``lifelines=True`` opts into the richer form).

``PlantUmlSequenceDiagramRenderer`` and ``MermaidSequenceDiagramRenderer`` (:mod:`mermaid`) share
one traversal (:mod:`sequence_walk`); ``PlantUmlSequenceGrammar`` here is the PlantUML-specific
literals that traversal composes with -- see :mod:`sequence_grammar` for the hook contract.
"""

from __future__ import annotations

from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk
from narrativetrace_diagrams.diagram_label import DiagramLabel
from narrativetrace_diagrams.sequence_grammar import LimitReason
from narrativetrace_diagrams.sequence_walk import collect_participants, render_sequence


class PlantUmlSequenceGrammar:
    """PlantUML grammar: ``->`` call arrows, ``-->`` returns, ``-[#red]->`` throws, ``hnote
    over`` for an in-flight outcome or a walk limit.

    ``lifelines`` is a Python-only extra with no counterpart in the Java reference this mirrors:
    when set, ``activate``/``deactivate`` emit real lifeline lines instead of the empty string.
    Because that flag is per-instance, unlike Mermaid's grammar this one is not a shared
    singleton -- each renderer constructs its own.
    """

    def __init__(self, lifelines: bool) -> None:
        self._lifelines = lifelines

    def header(self) -> str:
        return "@startuml\n"

    def participant(self, label: DiagramLabel) -> str:
        return f"participant {label.text}\n"

    def call_arrow(
        self, caller: DiagramLabel, target: DiagramLabel, signature: DiagramLabel
    ) -> str:
        return f"{caller.text} -> {target.text}: {signature.text}\n"

    def activate(self, target: DiagramLabel) -> str:
        return f"activate {target.text}\n" if self._lifelines else ""

    def return_arrow(
        self, target: DiagramLabel, caller: DiagramLabel, message: DiagramLabel
    ) -> str:
        return f"{target.text} --> {caller.text}: {message.text}\n"

    def throw_arrow(
        self, target: DiagramLabel, caller: DiagramLabel, exception_type: DiagramLabel
    ) -> str:
        return f"{target.text} -[#red]-> {caller.text}: {exception_type.text}\n"

    def deactivate(self, target: DiagramLabel) -> str:
        return f"deactivate {target.text}\n" if self._lifelines else ""

    def incomplete(self, target: DiagramLabel) -> str:
        return f"hnote over {target.text} : in-flight\n"

    def limited_note(self, target: DiagramLabel, reason: LimitReason) -> str:
        return f"hnote over {target.text} : {reason}\n"

    def footer(self) -> str:
        return "@enduml"


class PlantUmlSequenceDiagramRenderer:
    """Renders a trace tree as a PlantUML ``@startuml`` sequence diagram."""

    def __init__(self, lifelines: bool = False) -> None:
        self._grammar = PlantUmlSequenceGrammar(lifelines)

    def render(self, tree: TraceTree) -> str:
        grammar = self._grammar
        parts = [grammar.header()]
        for participant in collect_participants(tree.roots):
            parts.append(grammar.participant(DiagramLabel.quoted_identifier(participant)))
        walk = TreeWalk()
        for root in tree.roots:
            render_sequence(root, grammar, DiagramLabel.quoted_identifier, parts, walk)
        parts.append(grammar.footer())
        return "".join(parts).rstrip()
