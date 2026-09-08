# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders a trace and writes it (and coupled extras) to disk.

The writing slice of Java ``TraceTestSupport`` / ``TraceFileWriter``. Empty traces write
nothing.

Format selection mirrors Java ``TraceTestSupport.renderForFormat``: ``text`` is framed with a
scenario header, ``mermaid`` and ``plantuml`` write that diagram *instead of* the Markdown trace,
and anything else is the Markdown document. Format names are matched case-insensitively (Java
``toLowerCase`` / ``equalsIgnoreCase``), so an ambient ``PlantUML`` behaves like ``plantuml``.

The core distribution is dependency-free, so the diagram renderers and the JSON exporter arrive as
optional ``json_exporter`` / ``diagram_renderer`` (Mermaid) / ``plantuml_renderer`` hooks — the
Python equivalent of Java injecting both ``NarrativeRenderer``s into the helper. Requesting a
diagram format without its hook raises rather than silently writing Markdown into a ``.mmd`` /
``.puml`` file. ``diagram_renderer`` additionally emits the coupled ``diagrams/<Class>/*.mmd``
companion that Markdown output carries alongside its sibling ``.json``.

Every write passes ``errors="replace"`` (a security fuzz suite finding, mirrors Java's
``TraceFileWriter`` fix): narration and scenario text reach this module without passing through
:func:`narrativetrace.escape.control_sanitize` first (it is prose an author wrote, not a captured
value), so a lone surrogate code point in it would otherwise raise ``UnicodeEncodeError`` from the
write itself. A written artifact carrying one replacement marker is readable; a failed write is a
failed run. (Divergence from Java's exact fix: Python's built-in ``errors="replace"`` substitutes
ASCII ``?`` on encode, where Java's ``CodingErrorAction.REPLACE`` substitutes U+FFFD -- the marker
spelling differs, the degrade-rather-than-crash contract does not.)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from narrativetrace.output.paths import diagram_file, extension_for_format, trace_directory
from narrativetrace.output.paths import file_slug as _file_slug
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.scenario import frame
from narrativetrace.tree import TraceTree
from narrativetrace.tree_canonical import export_canonical_entries


@dataclass(frozen=True, slots=True)
class TraceArtifact:
    """Where and in what format one test's trace should be written.

    ``canonical`` opts into the extra ``<test>.canonical.json`` machine artifact — off by default
    because it exists for conformance runners and other runtimes, not for a developer reading a
    failure.
    """

    base_dir: Path
    class_name: str
    method_name: str
    fmt: str = "markdown"
    canonical: bool = False


@dataclass(slots=True)
class WriteResult:
    """Paths written for one trace and the framed console echo."""

    files: list[Path]
    console_echo: str


_DIAGRAM_FORMATS = ("mermaid", "plantuml")


def _render_primary(
    tree: TraceTree,
    metadata: TraceMetadata,
    fmt: str,
    diagram_renderer: Callable[[TraceTree], str] | None,
    plantuml_renderer: Callable[[TraceTree], str] | None,
) -> str:
    """Selects the renderer named by ``fmt`` (Java ``TraceTestSupport.renderForFormat``).

    ``fmt`` is expected already case-folded — :func:`write_trace` lowercases once at the boundary.
    """
    if fmt == "text":
        return f"{frame(metadata.scenario)}\n\n{IndentedTextRenderer().render(tree)}\n"
    if fmt == "mermaid" and diagram_renderer is not None:
        return diagram_renderer(tree) + "\n"
    if fmt == "plantuml" and plantuml_renderer is not None:
        return plantuml_renderer(tree) + "\n"
    return MarkdownRenderer().render_document(tree, metadata) + "\n"


def _require_diagram_renderer(
    fmt: str,
    diagram_renderer: Callable[[TraceTree], str] | None,
    plantuml_renderer: Callable[[TraceTree], str] | None,
) -> None:
    """Fails loudly rather than writing a Markdown document into a ``.mmd``/``.puml`` file."""
    supplied = diagram_renderer if fmt == "mermaid" else plantuml_renderer
    if fmt in _DIAGRAM_FORMATS and supplied is None:
        raise ValueError(f"format {fmt!r} requires the matching diagram renderer hook")


def write_trace(
    tree: TraceTree,
    metadata: TraceMetadata,
    artifact: TraceArtifact,
    *,
    json_exporter: Callable[[TraceTree], str] | None = None,
    diagram_renderer: Callable[[TraceTree], str] | None = None,
    plantuml_renderer: Callable[[TraceTree], str] | None = None,
) -> WriteResult:
    """Writes the primary trace file (+ markdown extras) and returns the written paths."""
    fmt = artifact.fmt.lower()
    _require_diagram_renderer(fmt, diagram_renderer, plantuml_renderer)
    if tree.is_empty:
        return WriteResult([], "")

    slug = _file_slug(artifact.method_name)
    directory = trace_directory(artifact.base_dir, artifact.class_name)
    directory.mkdir(parents=True, exist_ok=True)
    primary = directory / f"{slug}{extension_for_format(fmt)}"
    content = _render_primary(tree, metadata, fmt, diagram_renderer, plantuml_renderer)
    primary.write_text(content, encoding="utf-8", errors="replace")
    written = [primary]

    if fmt == "markdown":
        written += _write_markdown_extras(
            tree, directory, slug, artifact, json_exporter, diagram_renderer
        )
    # Independent of format: the canonical artifact is the machine contract, and a run that
    # switched to `text` or `mermaid` for humans still owes a conformance runner its entries.
    if artifact.canonical:
        written.append(_write_canonical(tree, directory, slug))

    trace_text = IndentedTextRenderer().render(tree)
    echo = f"{frame(metadata.scenario)}\n\nExecution trace:\n{trace_text}\nTrace written: {primary}"
    return WriteResult(written, echo)


def _write_canonical(tree: TraceTree, directory: Path, slug: str) -> Path:
    """Writes ``<slug>.canonical.json``: the flat entry array ``entry.schema.json`` validates."""
    path = directory / f"{slug}.canonical.json"
    path.write_text(export_canonical_entries(tree), encoding="utf-8", errors="replace")
    return path


def _write_markdown_extras(
    tree: TraceTree,
    directory: Path,
    slug: str,
    artifact: TraceArtifact,
    json_exporter: Callable[[TraceTree], str] | None,
    diagram_renderer: Callable[[TraceTree], str] | None,
) -> list[Path]:
    extras: list[Path] = []
    if json_exporter is not None:
        json_path = directory / f"{slug}.json"
        json_path.write_text(json_exporter(tree), encoding="utf-8", errors="replace")
        extras.append(json_path)
    if diagram_renderer is not None:
        mmd_path = diagram_file(artifact.base_dir, artifact.class_name, artifact.method_name)
        mmd_path.parent.mkdir(parents=True, exist_ok=True)
        mmd_path.write_text(diagram_renderer(tree), encoding="utf-8", errors="replace")
        extras.append(mmd_path)
    return extras
