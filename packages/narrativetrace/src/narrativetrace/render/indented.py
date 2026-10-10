# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Plain-text renderer using tree indentation and arrow notation.

``IndentedTextRenderer`` — the console/pytest-failure renderer. Errors render as
``!! Type: message | error_context``; redacted params as ``[REDACTED]``; narration as ``// ...``.
Every span line ends with its span id (``#1.3``, :mod:`~narrativetrace.render.span_id`) — the same
id every other flavour prints for that call.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.escape import control_sanitize
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.concurrency import analyze, partition
from narrativetrace.render.span_id import SpanCursor, concurrent_order, ids_of
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk

_NANOS_PER_MILLI = 1_000_000


def _return_text(value: str | None) -> str:
    return "null" if value is None else value


def _thread_label(node: TraceNode) -> str:
    info = node.concurrency
    if info is None:
        return ""
    return info.thread_name if info.thread_name is not None else (info.task_label or "")


def _header(sig: MethodSignature) -> str:
    params = ", ".join(_render_param(p) for p in sig.parameters)
    class_name = control_sanitize(sig.class_name)
    method_name = control_sanitize(sig.method_name)
    return f"{class_name}.{method_name}({params})"


def _render_param(param: ParameterCapture) -> str:
    name = control_sanitize(param.name)
    if param.redacted:
        return f"{name}: [REDACTED]"
    return f"{name}: {param.rendered_value}"


def _exception_type(exception: BaseException) -> str:
    return control_sanitize(type(exception).__name__)


@dataclass(frozen=True, slots=True)
class _Line:
    """Where one span is printed: the prefix of its own line, the prefix its children and
    narration continue under, and its span id."""

    prefix: str
    cont: str
    span_id: str


def _append_trace_header(tree: TraceTree, parts: list[str]) -> None:
    """Opens with ``trace: bold elk soars (a1b2c3d)`` -- the trace's own three-word phrase plus
    the first 7 hex characters of its id -- so a console reader can name and locate the trace
    without cross-referencing a separate identifier line (2026-09-13 ruling, item 4). Silent when
    :attr:`TraceTree.trace_id` is ``None`` (an empty tree): nothing here is invented.

    This is the trace's OWN name, unrelated to the test-suite run name a caller may thread through
    a suite footer and manifest -- see :class:`~narrativetrace.output.run_identity.RunIdentity`.
    Neither ever reaches the structural ``.nt`` text.
    """
    trace_id = tree.trace_id
    if trace_id is None:
        return
    parts.append(f"trace: {trace_id.human_name()} ({trace_id.value[:7]})\n\n")


class IndentedTextRenderer:
    """Renders a trace tree as an indented ASCII tree."""

    def render(self, tree: TraceTree) -> str:
        parts: list[str] = []
        _append_trace_header(tree, parts)
        walk = TreeWalk()
        for root, root_id in zip(tree.roots, ids_of(tree.roots, None), strict=True):
            self._render_node(root, _Line("", "", root_id), parts, walk)
        return "".join(parts).rstrip()

    def _render_node(self, node: TraceNode, line: _Line, parts: list[str], walk: TreeWalk) -> None:
        stop_reason = walk.stop_reason(node)
        if not node.children or stop_reason is not None:
            self._render_leaf_node(node, line, stop_reason, parts)
        else:
            self._render_branch_node(node, line, parts, walk)

    def _render_leaf_node(
        self, node: TraceNode, line: _Line, stop_reason: str | None, parts: list[str]
    ) -> None:
        """A node with no children, or one whose children the walk stopped short of visiting --
        the node still contributes its own header/outcome, only its subtree is cut off. The span
        id ends the line."""
        sig = node.signature
        parts.append(f"{line.prefix}{_header(sig)}")
        self._render_outcome_inline(node.outcome, sig, parts)
        self._render_duration(node, parts)
        if stop_reason is not None and node.children:
            parts.append(f" {stop_reason}")
        parts.append(f" {line.span_id}\n")

    def _render_branch_node(
        self, node: TraceNode, line: _Line, parts: list[str], walk: TreeWalk
    ) -> None:
        walk.enter(node)
        try:
            sig = node.signature
            cont_prefix = line.cont
            parts.append(f"{line.prefix}{_header(sig)} {line.span_id}\n")
            self._render_narration(sig, cont_prefix, parts)
            self._render_children(node.children, cont_prefix, line.span_id, parts, walk)
            parts.append(f"{cont_prefix}└── ")
            self._render_outcome_closing(node.outcome, sig, parts)
            self._render_duration(node, parts)
            parts.append("\n")
        finally:
            walk.exit(node)

    def _render_children(
        self,
        children: list[TraceNode],
        cont_prefix: str,
        parent_id: str,
        parts: list[str],
        walk: TreeWalk,
    ) -> None:
        """One sibling list, each span taking its id in the order it is laid out."""
        ids = SpanCursor(parent_id)
        for segment in partition(children):
            if segment.group_id is None:
                line = _Line(f"{cont_prefix}├── ", f"{cont_prefix}│   ", ids.next())
                self._render_node(segment.nodes[0], line, parts, walk)
            elif segment.is_fire_and_forget():
                launch = _Line(cont_prefix, cont_prefix, ids.next())
                self._render_fire_and_forget(segment.nodes[0], launch, parts, walk)
            else:
                self._render_concurrent_group(segment.nodes, cont_prefix, ids, parts)

    def _render_fire_and_forget(
        self, launcher: TraceNode, launch: _Line, parts: list[str], walk: TreeWalk
    ) -> None:
        """The launch takes one position; its id ends the marker line, and the launched work is
        laid out under it like any other sibling list (a fork in it keeps its marker). The
        launcher goes through the walk like any node: a cycle or the depth limit ends it."""
        cont_prefix = launch.cont
        parts.append(f"{cont_prefix}├── ⤳ fire-and-forget")
        if launcher.concurrency is not None:
            parts.append(f" [thread: {_thread_label(launcher)}]")
        stop_reason = walk.stop_reason(launcher)
        if stop_reason is not None:
            parts.append(f" {stop_reason} {launch.span_id}\n")
            return
        parts.append(f" {launch.span_id}\n")
        if not launcher.children:
            parts.append(f"{cont_prefix}│       [launched, result not captured]\n")
            return
        walk.enter(launcher)
        try:
            self._render_children(
                launcher.children, f"{cont_prefix}│   ", launch.span_id, parts, walk
            )
        finally:
            walk.exit(launcher)

    def _render_concurrent_group(
        self, members: list[TraceNode], cont_prefix: str, ids: SpanCursor, parts: list[str]
    ) -> None:
        analysis = analyze(members)
        parts.append(f"{cont_prefix}├── ⑂ fork [{len(members)} tasks]\n")
        for member in sorted(members, key=concurrent_order):
            member_line = _Line(f"{cont_prefix}│   ", f"{cont_prefix}│   ", ids.next())
            self._render_concurrent_member(member, member_line, analysis.is_sequential_async, parts)
        wall_ms = max((m.duration_nanos for m in members), default=0) // _NANOS_PER_MILLI
        parts.append(f"{cont_prefix}├── ⑃ join — {wall_ms}ms\n")
        if analysis.is_sequential_async:
            parts.append(
                f"{cont_prefix}├── ⚡ Sequential async: total {analysis.total_millis}ms, "
                f"parallelizable to ~{analysis.parallelizable_millis}ms\n"
            )

    def _render_concurrent_member(
        self, node: TraceNode, line: _Line, sequential_async: bool, parts: list[str]
    ) -> None:
        sig = node.signature
        cont_prefix = line.cont
        parts.append(f"{cont_prefix}├── ↦ {_header(sig)}")
        self._render_outcome_inline(node.outcome, sig, parts)
        self._render_duration(node, parts)
        parts.append(f" {line.span_id}\n")
        if node.concurrency is not None:
            suffix = "] [async, awaited sequentially]\n" if sequential_async else "]\n"
            parts.append(f"{cont_prefix}│       [thread: {_thread_label(node)}{suffix}")

    def _render_outcome_inline(
        self, outcome: TraceOutcome | None, sig: MethodSignature, parts: list[str]
    ) -> None:
        if isinstance(outcome, Returned):
            parts.append(f" → {_return_text(outcome.rendered_value)}")
        elif isinstance(outcome, Threw):
            message = control_sanitize(str(outcome.exception))
            parts.append(f" !! {_exception_type(outcome.exception)}: {message}")
            if sig.error_context is not None:
                parts.append(f" | {control_sanitize(sig.error_context)}")
        elif isinstance(outcome, Incomplete):
            parts.append(" ⏳ in-flight")

    def _render_outcome_closing(
        self, outcome: TraceOutcome | None, sig: MethodSignature, parts: list[str]
    ) -> None:
        if isinstance(outcome, Returned):
            parts.append(f"→ {_return_text(outcome.rendered_value)}")
        elif isinstance(outcome, Threw):
            message = control_sanitize(str(outcome.exception))
            parts.append(f"!! {_exception_type(outcome.exception)}: {message}")
            if sig.error_context is not None:
                parts.append(f" | {control_sanitize(sig.error_context)}")
        elif isinstance(outcome, Incomplete):
            parts.append("⏳ in-flight")

    def _render_narration(self, sig: MethodSignature, cont_prefix: str, parts: list[str]) -> None:
        if sig.narration is not None:
            parts.append(f"{cont_prefix}│   // {control_sanitize(sig.narration)}\n")

    def _render_duration(self, node: TraceNode, parts: list[str]) -> None:
        if node.duration_nanos > 0:
            parts.append(f" — {node.duration_millis}ms")
