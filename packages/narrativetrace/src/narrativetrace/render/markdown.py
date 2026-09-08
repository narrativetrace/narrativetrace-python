# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Markdown renderer with an optional document wrapper.

``MarkdownRenderer``: headings, nested call lists, timing (``— Nms``, slow marker on a
strict ``>`` threshold), narration, error blocks, and concurrency annotations, optionally wrapped
in YAML frontmatter.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.escape import markdown_code, markdown_text
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.concurrency import analyze, partition
from narrativetrace.render.frontmatter import FrontmatterBuilder
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
        for root in tree.roots:
            self._render_node(root, 0, ctx)
        return "".join(ctx.parts).rstrip()

    def render_document(self, tree: TraceTree, metadata: TraceMetadata) -> str:
        """Renders a full document: frontmatter + header + call flow."""
        parts: list[str] = [FrontmatterBuilder().scenario(metadata.scenario).build(tree)]
        self._render_header(tree, metadata, parts)
        ctx = _RenderCtx(parts, ValueReferenceIndex.build(tree), TreeWalk())
        for root in tree.roots:
            self._render_node(root, 0, ctx)
        return "".join(ctx.parts).rstrip()

    def _render_header(self, tree: TraceTree, metadata: TraceMetadata, parts: list[str]) -> None:
        if not tree.roots:
            return
        sig = tree.roots[0].signature
        duration_ms = tree.roots[0].duration_millis
        heading = f"{markdown_text(sig.class_name)}.{markdown_text(sig.method_name)}"
        parts.append(f"\n## Trace: {heading}\n\n")
        parts.append(f"**Scenario:** {markdown_text(metadata.scenario)}\n")
        parts.append(
            f"**Duration:** {duration_ms}ms | **Result:** {metadata.result.display_name}\n\n"
        )
        parts.append("### Call Flow\n\n")

    def _render_node(self, node: TraceNode, depth: int, ctx: _RenderCtx) -> None:
        self._render_entry(node, depth, "- ", ctx)

    def _render_entry(self, node: TraceNode, depth: int, prefix: str, ctx: _RenderCtx) -> None:
        stop_reason = ctx.walk.stop_reason(node)
        if not node.children or stop_reason is not None:
            self._render_leaf_entry(node, prefix, stop_reason, depth, ctx)
        else:
            self._render_branch_entry(node, prefix, depth, ctx)

    def _render_leaf_entry(
        self, node: TraceNode, prefix: str, stop_reason: str | None, depth: int, ctx: _RenderCtx
    ) -> None:
        """A node with no children, or one whose children the walk stopped short of visiting --
        the node still contributes its own header/outcome, only its subtree is cut off."""
        indent = "  " * depth
        method_call = self._format_method_call(node.signature, ctx.refs)
        ctx.parts.append(f"{indent}{prefix}{method_call}")
        self._render_outcome_inline(node.outcome, node.signature, depth, ctx.parts, ctx.refs)
        self._render_duration(node, ctx.parts)
        if stop_reason is not None and node.children:
            ctx.parts.append(f" {stop_reason}")
        ctx.parts.append("\n")

    def _render_branch_entry(
        self, node: TraceNode, prefix: str, depth: int, ctx: _RenderCtx
    ) -> None:
        ctx.walk.enter(node)
        try:
            indent = "  " * depth
            sig = node.signature
            method_call = self._format_method_call(sig, ctx.refs)
            ctx.parts.append(f"{indent}{prefix}{method_call}")
            self._render_duration(node, ctx.parts)
            ctx.parts.append("\n")
            self._render_narration(sig, indent, ctx.parts)
            self._render_children(node.children, depth + 1, ctx)
            ctx.parts.append(f"{indent}  - ")
            self._render_outcome_closing(node.outcome, sig, depth, ctx.parts, ctx.refs)
            ctx.parts.append("\n")
        finally:
            ctx.walk.exit(node)

    def _render_children(self, children: list[TraceNode], depth: int, ctx: _RenderCtx) -> None:
        for segment in partition(children):
            if segment.group_id is None:
                self._render_node(segment.nodes[0], depth, ctx)
            elif segment.is_fire_and_forget():
                self._render_fire_and_forget(segment.nodes[0], depth, ctx)
            else:
                self._render_concurrent_group(segment.nodes, depth, ctx)

    def _render_fire_and_forget(self, launcher: TraceNode, depth: int, ctx: _RenderCtx) -> None:
        indent = "  " * depth
        ctx.parts.append(f"{indent}- ⤳ fire-and-forget")
        if launcher.concurrency is not None:
            ctx.parts.append(f" [thread: {_thread_label(launcher)}]")
        ctx.parts.append("\n")
        if not launcher.children:
            ctx.parts.append(f"{indent}  [launched, result not captured]\n")
        else:
            for child in launcher.children:
                self._render_node(child, depth + 1, ctx)

    def _render_concurrent_group(
        self, members: list[TraceNode], depth: int, ctx: _RenderCtx
    ) -> None:
        indent = "  " * depth
        analysis = analyze(members)
        ctx.parts.append(f"{indent}- ⑂ fork [{len(members)} tasks]\n")
        for member in sorted(members, key=_sig_key):
            self._render_concurrent_member(member, depth + 1, analysis.is_sequential_async, ctx)
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
        self, node: TraceNode, depth: int, sequential_async: bool, ctx: _RenderCtx
    ) -> None:
        self._render_entry(node, depth, "- ↦ ", ctx)
        if node.concurrency is not None:
            indent = "  " * depth
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


def _sig_key(node: TraceNode) -> str:
    return f"{node.signature.class_name}.{node.signature.method_name}"


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
