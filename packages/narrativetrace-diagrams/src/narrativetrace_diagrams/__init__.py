# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Mermaid and PlantUML sequence-diagram renderers for narrativetrace traces."""

from narrativetrace_diagrams.mermaid import MermaidSequenceDiagramRenderer
from narrativetrace_diagrams.plantuml import PlantUmlSequenceDiagramRenderer
from narrativetrace_diagrams.text import diagram_message, quote_if_needed

__version__ = "0.1.0"

__all__ = [
    "MermaidSequenceDiagramRenderer",
    "PlantUmlSequenceDiagramRenderer",
    "diagram_message",
    "quote_if_needed",
]
