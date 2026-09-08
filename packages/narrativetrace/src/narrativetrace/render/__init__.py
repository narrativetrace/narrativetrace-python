# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Trace-tree renderers: Markdown, IndentedText, Prose (+ frontmatter, scenario framing)."""

from narrativetrace.render.base import NarrativeRenderer, TraceMetadata
from narrativetrace.render.frontmatter import FrontmatterBuilder
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.scenario import frame, humanize
from narrativetrace.render.scenario_result import ScenarioResult

__all__ = [
    "FrontmatterBuilder",
    "IndentedTextRenderer",
    "MarkdownRenderer",
    "NarrativeRenderer",
    "ProseRenderer",
    "ScenarioResult",
    "TraceMetadata",
    "frame",
    "humanize",
]
