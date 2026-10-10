# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Markdown renderer with an optional document wrapper.

``MarkdownRenderer``: headings, nested call lists, timing (``— Nms``, slow marker on a
strict ``>`` threshold), narration, error blocks, and concurrency annotations, optionally wrapped
in YAML frontmatter. Every span's call line ends with its span id (``#1.3``,
:mod:`~narrativetrace.render.span_id`) — the same id every other flavour prints for that call.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.escape import markdown_code, markdown_text
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.concurrency import analyze, partition
from narrativetrace.render.frontmatter import FrontmatterBuilder
from narrativetrace.render.span_id import SpanCursor, concurrent_order
from narrativetrace.render.value_reference import ValueReferenceIndex
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk

_NANOS_PER_MILLI = 1_000_000
_DEFAULT_SLOW_THRESHOLD_MS = 200


def _return_text(value: str | None) -> str:
    return "null" if value is None else value


def _display_return(value: str | None, refs: ValueReferenceIndex) -> str:
    """Return value through the reference index; a void return keeps its ``null`` literal."""
    return "null" if value is None else (refs.display(value) or value)


def _thread_label(node: TraceNode) -> str:
    info = node.concurrency
    if info is None:
        return ""
    return info.thread_name if info.thread_name is not None else (info.task_label or "")


@dataclass(frozen=True, slots=True)
class _Entry:
    """Where one span is printed: its list depth, its bullet (``- `` or ``- ↦ ``) and its span
    id, which ends the call line."""

    depth: int
    prefix: str
    span_id: str


@dataclass(slots=True)
class _RenderCtx:
    """The three things every recursive rendering call carries together: the output accumulator,
    the value-reference index, and the shared depth/cycle walk state -- bundled so a call site
    threading them through a mutually-recursive descent stays under the argument-count gate."""

    parts: list[str]
    refs: ValueReferenceIndex
    walk: TreeWalk


class MarkdownRenderer:
    """Renders a trace tree to Markdown (body only, or a full document)."""

    def __init__(self, slow_threshold_ms: int = _DEFAULT_SLOW_THRESHOLD_MS) -> None:
        self._slow_threshold_ms = slow_threshold_ms

    def render(self, tree: TraceTree) -> str:
        """Renders the call-flow body (no frontmatter)."""
        ctx = _RenderCtx([], ValueReferenceIndex.build(tree), TreeWalk())
        self._render_children(tree.roots, 0, None, ctx)
        return "".join(ctx.parts).rstrip()

    def render_document(self, tree: TraceTree, metadata: TraceMetadata) -> str:
        """Renders a full document: frontmatter + header + call flow."""
        frontmatter = (
            FrontmatterBuilder().scenario(metadata.scenario).run_name(metadata.run_name).build(tree)
        )
        parts: list[str] = [frontmatter]
        self._render_header(tree, metadata, parts)
        ctx = _RenderCtx(parts, ValueReferenceIndex.build(tree), TreeWalk())
        self._render_children(tree.roots, 0, None, ctx)
        return "".join(ctx.parts).rstrip()

    def _render_header(self, tree: TraceTree, metadata: TraceMetadata, parts: list[str]) -> None:
        if not tree.roots:
            return
        sig = tree.roots[0].signature
        duration_ms = tree.roots[0].duration_millis
        heading = f"{markdown_text(sig.class_name)}.{markdown_text(sig.method_name)}"
        parts.append(f"\n## Trace: {_trace_phrase_prefix(tree)}{heading}\n\n")
        parts.append(f"**Scenario:** {markdown_text(metadata.scenario)}\n")
        parts.append(
            f"**Duration:** {duration_ms}ms | **Result:** {metadata.result.display_name}\n\n"
        )
        parts.append("### Call Flow\n\n")

    def _render_entry(self, node: TraceNode, entry: _Entry, ctx: _RenderCtx) -> None:
        stop_reason = ctx.walk.stop_reason(node)
        if not node.children or stop_reason is not None:
            self._render_leaf_entry(node, entry, stop_reason, ctx)
        else:
            self._render_branch_entry(node, entry, ctx)

    def _render_leaf_entry(
        self, node: TraceNode, entry: _Entry, stop_reason: str | None, ctx: _RenderCtx
    ) -> None:
        """A node with no children, or one whose children the walk stopped short of visiting --
        the node still contributes its own header/outcome, only its subtree is cut off.

        The span id ends the call line — which, for a thrown outcome, is BEFORE its blockquote,
        so the id stays on the line that names the call."""
        depth = entry.depth
        method_call = self._format_method_call(node.signature, ctx.refs)
        ctx.parts.append(f"{'  ' * depth}{entry.prefix}{method_call}")
        opens_a_block = isinstance(node.outcome, Threw)
        if opens_a_block:
            ctx.parts.append(f" {entry.span_id}")
        self._render_outcome_inline(node.outcome, node.signature, depth, ctx.parts, ctx.refs)
        self._render_duration(node, ctx.parts)
        if stop_reason is not None and node.children:
            ctx.parts.append(f" {stop_reason}")
        if not opens_a_block:
            ctx.parts.append(f" {entry.span_id}")
        ctx.parts.append("\n")

    def _render_branch_entry(self, node: TraceNode, entry: _Entry, ctx: _RenderCtx) -> None:
        ctx.walk.enter(node)
        try:
            depth = entry.depth
            indent = "  " * depth
            sig = node.signature
            method_call = self._format_method_call(sig, ctx.refs)
            ctx.parts.append(f"{indent}{entry.prefix}{method_call}")
            self._render_duration(node, ctx.parts)
            ctx.parts.append(f" {entry.span_id}\n")
            self._render_narration(sig, indent, ctx.parts)
            self._render_children(node.children, depth + 1, entry.span_id, ctx)
            ctx.parts.append(f"{indent}  - ")
            self._render_outcome_closing(node.outcome, sig, depth, ctx.parts, ctx.refs)
            ctx.parts.append("\n")
        finally:
            ctx.walk.exit(node)

    def _render_children(
        self, children: list[TraceNode], depth: int, parent_id: str | None, ctx: _RenderCtx
    ) -> None:
        """One sibling list (a tree's roots when ``parent_id`` is ``None``), each span taking its
        id in the order it is laid out."""
        ids = SpanCursor(parent_id)
        for segment in partition(children):
            if segment.group_id is None:
                self._render_entry(segment.nodes[0], _Entry(depth, "- ", ids.next()), ctx)
            elif segment.is_fire_and_forget():
                self._render_fire_and_forget(segment.nodes[0], depth, ids.next(), ctx)
            else:
                self._render_concurrent_group(segment.nodes, depth, ids, ctx)

    def _render_fire_and_forget(
        self, launcher: TraceNode, depth: int, launcher_id: str, ctx: _RenderCtx
    ) -> None:
        """The launch takes one position; its id ends the marker line, and the launched work is
        laid out under it like any other sibling list (a fork in it keeps its marker). The
        launcher goes through the walk like any node: a cycle or the depth limit ends it."""
        indent = "  " * depth
        ctx.parts.append(f"{indent}- ⤳ fire-and-forget")
        if launcher.concurrency is not None:
            ctx.parts.append(f" [thread: {_thread_label(launcher)}]")
        stop_reason = ctx.walk.stop_reason(launcher)
        if stop_reason is not None:
            ctx.parts.append(f" {stop_reason} {launcher_id}\n")
            return
        ctx.parts.append(f" {launcher_id}\n")
        if not launcher.children:
            ctx.parts.append(f"{indent}  [launched, result not captured]\n")
            return
        ctx.walk.enter(launcher)
        try:
            self._render_children(launcher.children, depth + 1, launcher_id, ctx)
        finally:
            ctx.walk.exit(launcher)

    def _render_concurrent_group(
        self, members: list[TraceNode], depth: int, ids: SpanCursor, ctx: _RenderCtx
    ) -> None:
        indent = "  " * depth
        analysis = analyze(members)
        ctx.parts.append(f"{indent}- ⑂ fork [{len(members)} tasks]\n")
        for member in sorted(members, key=concurrent_order):
            entry = _Entry(depth + 1, "- ↦ ", ids.next())
            self._render_concurrent_member(member, entry, analysis.is_sequential_async, ctx)
        wall_ms = max((m.duration_nanos for m in members), default=0) // _NANOS_PER_MILLI
        ctx.parts.append(f"{indent}- ⑃ join — {wall_ms}ms")
        _append_wait_analysis(members, ctx.parts)
        ctx.parts.append("\n")
        if analysis.is_sequential_async:
            ctx.parts.append(
                f"{indent}- ⚡ Sequential async: total {analysis.total_millis}ms, "
                f"parallelizable to ~{analysis.parallelizable_millis}ms\n"
            )

    def _render_concurrent_member(
        self, node: TraceNode, entry: _Entry, sequential_async: bool, ctx: _RenderCtx
    ) -> None:
        self._render_entry(node, entry, ctx)
        if node.concurrency is not None:
            indent = "  " * entry.depth
            suffix = "] [async, awaited sequentially]\n" if sequential_async else "]\n"
            ctx.parts.append(f"{indent}      [thread: {_thread_label(node)}{suffix}")

    def _render_outcome_inline(
        self,
        outcome: TraceOutcome | None,
        sig: MethodSignature,
        depth: int,
        parts: list[str],
        refs: ValueReferenceIndex,
    ) -> None:
        if isinstance(outcome, Returned):
            parts.append(f" → {markdown_code(_display_return(outcome.rendered_value, refs))}")
        elif isinstance(outcome, Threw):
            error_indent = "  " * (depth + 1)
            exc_type = markdown_code(type(outcome.exception).__name__)
            message = markdown_text(str(outcome.exception))
            parts.append(f"\n\n{error_indent}> ❌ {exc_type}: {message}")
            if sig.error_context is not None:
                parts.append(f"\n{error_indent}> {markdown_text(sig.error_context)}")
        elif isinstance(outcome, Incomplete):
            parts.append(" ⏳ in-flight")

    def _render_outcome_closing(
        self,
        outcome: TraceOutcome | None,
        sig: MethodSignature,
        depth: int,
        parts: list[str],
        refs: ValueReferenceIndex,
    ) -> None:
        if isinstance(outcome, Returned):
            parts.append(f"→ {markdown_code(_display_return(outcome.rendered_value, refs))}")
        elif isinstance(outcome, Threw):
            error_indent = "  " * (depth + 1)
            exc_type = markdown_code(type(outcome.exception).__name__)
            message = markdown_text(str(outcome.exception))
            parts.append(f"❌ {exc_type}: {message}")
            if sig.error_context is not None:
                parts.append(f"\n{error_indent}> {markdown_text(sig.error_context)}")
        elif isinstance(outcome, Incomplete):
            parts.append("⏳ in-flight")

    def _render_narration(self, sig: MethodSignature, indent: str, parts: list[str]) -> None:
        if sig.narration is not None:
            parts.append(f"{indent}  *{markdown_text(sig.narration)}*\n")

    def _render_duration(self, node: TraceNode, parts: list[str]) -> None:
        if node.duration_nanos > 0:
            millis = node.duration_millis
            parts.append(f" — {millis}ms")
            if millis > self._slow_threshold_ms:
                parts.append(" ⚠️ slow")

    def _format_method_call(self, sig: MethodSignature, refs: ValueReferenceIndex) -> str:
        params = ", ".join(_render_param(p, refs) for p in sig.parameters)
        class_name = markdown_text(sig.class_name)
        method_name = markdown_text(sig.method_name)
        return f"**{class_name}.{method_name}**({params})"


def _trace_phrase_prefix(tree: TraceTree) -> str:
    """The trace's own three-word phrase plus a trailing separator (``"bold elk soars — "``), or
    empty when :attr:`TraceTree.trace_id` is ``None`` -- the frontmatter already carries the
    phrase (and the raw id) as ``trace_name:``/``trace_id:``; this is the same phrase in the
    document's own title line (2026-09-13 ruling, item 4)."""
    trace_id = tree.trace_id
    return "" if trace_id is None else f"{trace_id.human_name()} — "


def _render_param(param: ParameterCapture, refs: ValueReferenceIndex) -> str:
    # A redacted capture keeps its marker without ever entering the reference index; only real
    # captured values are deduplicated (Java ValueReferenceIndex._count_node skips redacted).
    name = markdown_text(param.name)
    if param.redacted:
        return f"{name}: `[REDACTED]`"
    return f"{name}: {markdown_code(refs.display(param.rendered_value) or '')}"


def _append_wait_analysis(members: list[TraceNode], parts: list[str]) -> None:
    if len(members) < 2:
        return
    slowest = max(members, key=lambda n: n.duration_nanos)
    fastest = min(members, key=lambda n: n.duration_nanos)
    wait_ms = (slowest.duration_nanos - fastest.duration_nanos) // _NANOS_PER_MILLI
    if wait_ms > 0:
        parts.append(
            f" (waited {wait_ms}ms for {slowest.signature.class_name} "
            f"after {fastest.signature.class_name})"
        )
