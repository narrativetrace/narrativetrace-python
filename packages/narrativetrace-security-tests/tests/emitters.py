# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Every output format this runtime ships, as one map (the shared ``Emitters`` map).

A test that names formats inline goes stale the day a format is added -- every oracle in this
package iterates :data:`EMITTERS` instead, so a new renderer is covered the moment it is added
here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from narrativetrace_diagrams import MermaidSequenceDiagramRenderer, PlantUmlSequenceDiagramRenderer

from narrativetrace.chapter import export_chapter
from narrativetrace.export import export_document
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.tree_canonical import export_canonical_entries

Emitter = Callable[[TraceTree, TraceMetadata], str]

_FIXED_INSTANT = datetime(2026, 1, 1, tzinfo=UTC)
"""``export_chapter`` stamps a live wall-clock timestamp by design (it is a chapter-completion
instant, not a pure function of the tree) -- a fixed clock is what its own ``clock`` parameter
exists for, so every property in this package (idempotence included) sees reproducible bytes."""


def captured_value_tree(rendered_value: str) -> TraceTree:
    """A one-node tree whose return value is already-rendered text -- the shape a real capture
    produces after ``ValueRenderer.render()`` has run (and therefore already control-sanitised)."""
    node = TraceNode(MethodSignature("HostileCase", "run", []), [], Returned(rendered_value))
    return TraceTree([node])


def tree_with_hostile_metadata(text: str) -> TraceTree:
    """Puts the fuzzer's bytes in ``class_name``, ``method_name``, and a parameter name at once
    (adversarial-audit mirror, F4, 2026-09-02, the shared ``treeWithHostileMetadata`` shape).
    These are *metadata* fields, not captured values -- fuzzing values alone (as every other tree
    builder in this module does) is structurally unable to reach the
    ``className``/``methodName``/parameter-name seam a renderer might interpolate without the
    escaping a rendered value already gets. Exception-type-name escaping is covered separately
    (``narrativetrace-diagrams``' ``TestMetadataInjection``, and the core renderer tests) rather
    than through this corpus-driven route: unlike these three plain ``str`` fields, an exception's
    type name is a real class's ``__name__``, which CPython itself refuses for a NUL byte or a
    lone surrogate -- exercising those two corpus cases through ``__name__`` would test CPython's
    own restriction, not this renderer's escaping."""
    node = TraceNode(
        MethodSignature(text, text, [ParameterCapture(text, '"v"')]),
        [],
        Threw(RuntimeError("boom")),
    )
    return TraceTree([node])


def tree_throwing(message: str) -> TraceTree:
    """A one-node tree that threw, so the exception-message rendering paths are exercised --
    unlike a captured value, an exception message never passes through ``ValueRenderer``."""
    node = TraceNode(MethodSignature("HostileCase", "run", []), [], Threw(RuntimeError(message)))
    return TraceTree([node])


def metadata_for(scenario: str) -> TraceMetadata:
    """Scenario/narration text -- unlike a captured value, this never passes through
    ``control_sanitize`` (a security fuzz suite finding's writer-layer fix exists for exactly this
    route)."""
    return TraceMetadata(scenario, ScenarioResult.SUCCESS)


EMITTERS: dict[str, Emitter] = {
    "markdown-document": lambda tree, meta: MarkdownRenderer().render_document(tree, meta),
    "markdown-body": lambda tree, _meta: MarkdownRenderer().render(tree),
    "indented-text": lambda tree, _meta: IndentedTextRenderer().render(tree),
    "prose": lambda tree, _meta: ProseRenderer().render(tree),
    "json-chapter-tree": export_document,
    "json-chapter": lambda tree, meta: export_chapter(tree, meta, clock=lambda: _FIXED_INSTANT),
    "canonical-entries": lambda tree, _meta: export_canonical_entries(tree),
    "mermaid": lambda tree, _meta: MermaidSequenceDiagramRenderer().render(tree),
    "plantuml": lambda tree, _meta: PlantUmlSequenceDiagramRenderer().render(tree),
}


def every_output(tree: TraceTree, metadata: TraceMetadata) -> dict[str, str]:
    """Drives every shipped emitter over the same tree/metadata pair."""
    return {name: emitter(tree, metadata) for name, emitter in EMITTERS.items()}
