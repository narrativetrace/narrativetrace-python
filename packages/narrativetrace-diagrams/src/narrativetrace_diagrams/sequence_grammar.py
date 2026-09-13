# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The per-format literals :mod:`sequence_walk` needs to render one trace tree as a sequence
diagram -- everything Mermaid and PlantUML disagree about, in one place.

INTENT: ``MermaidSequenceDiagramRenderer`` and ``PlantUmlSequenceDiagramRenderer`` share one
traversal (:mod:`sequence_walk`); the two formats differ only in header/footer text, participant
declaration syntax, arrow syntax, return/throw/limited-node notation, PlantUML's optional
lifeline activation, and -- for Mermaid's alias mode -- how a class name becomes the label an
arrow names (a walk concern, not a grammar one; see :func:`sequence_walk.render_sequence`). Every
hook here is a pure function of its inputs.

Every hook that carries trace-derived text takes a
:class:`~narrativetrace_diagrams.diagram_label.DiagramLabel`, never a ``str`` -- a grammar
implementation cannot receive a raw trace string; only :mod:`sequence_walk` ever turns a raw
class name into a label, through the label-mapping function each renderer supplies, before any
hook here is called. ``limited_note``'s ``reason`` is the one exception: it is never trace-derived
(it is one of :mod:`narrativetrace.tree_walk`'s own fixed markers), so it is typed as
``LimitReason`` -- a distinct nominal type from ``str`` -- rather than a
:class:`~narrativetrace_diagrams.diagram_label.DiagramLabel`, mirroring the Java reference's
``TreeWalk.Reason`` exception in its own shape test.

``activate``/``deactivate`` have no counterpart in the Java reference: they exist only for
PlantUML's optional lifelines (a Python-only extra) and are no-ops in Mermaid's grammar.
"""

from __future__ import annotations

from typing import NewType, Protocol

from narrativetrace_diagrams.diagram_label import DiagramLabel

LimitReason = NewType("LimitReason", str)
"""The reason :mod:`narrativetrace.tree_walk` stopped descending into a node: one of its own
``CYCLE_MARKER``/``DEPTH_LIMIT_MARKER`` constants -- a fixed, runtime-defined marker, never
trace-derived text, so it never needs to pass through :mod:`narrativetrace_diagrams.text`."""


class SequenceGrammar(Protocol):
    """Every hook :mod:`sequence_walk` needs to render one trace tree as a sequence diagram."""

    def header(self) -> str:
        """The opening line(s) of the diagram, before any participant declaration."""
        ...

    def participant(self, label: DiagramLabel) -> str:
        """One participant declaration line, already composed (plain display name, or Mermaid's
        alias)."""
        ...

    def call_arrow(
        self, caller: DiagramLabel, target: DiagramLabel, signature: DiagramLabel
    ) -> str:
        """One call arrow, caller to target, naming the call signature."""
        ...

    def activate(self, target: DiagramLabel) -> str:
        """A lifeline-activation line for ``target``, or ``""`` when the grammar has no
        lifelines."""
        ...

    def return_arrow(
        self, target: DiagramLabel, caller: DiagramLabel, message: DiagramLabel
    ) -> str:
        """One return arrow, target back to caller, carrying the return message."""
        ...

    def throw_arrow(
        self, target: DiagramLabel, caller: DiagramLabel, exception_type: DiagramLabel
    ) -> str:
        """One throw arrow, target back to caller, naming the exception type."""
        ...

    def deactivate(self, target: DiagramLabel) -> str:
        """A lifeline-deactivation line for ``target``, or ``""`` when the grammar has no
        lifelines."""
        ...

    def incomplete(self, target: DiagramLabel) -> str:
        """The note for a node whose outcome never arrived (an in-flight call)."""
        ...

    def limited_note(self, target: DiagramLabel, reason: LimitReason) -> str:
        """The note appended after a node the walk stopped at instead of descending into."""
        ...

    def footer(self) -> str:
        """The closing line(s) of the diagram, after every root has been walked."""
        ...
