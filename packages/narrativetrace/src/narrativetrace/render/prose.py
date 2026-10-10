# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renderer that turns traces into short prose paragraphs.

``ProseRenderer``: ``failed to <action>`` error phrasing, parent ``:`` structure with a
closing ``Returned X.`` sentence, and ``In the background (#id):`` / ``Concurrently:`` labels.
Every span is named by its span id in parentheses (``(#1.3)``,
:mod:`~narrativetrace.render.span_id`) — the id every other flavour prints for that call.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render import camel
from narrativetrace.render.concurrency import analyze, partition
from narrativetrace.render.span_id import SpanCursor, concurrent_order
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk


def _render_param(param: ParameterCapture) -> str:
    name = control_sanitize(param.name)
    if param.redacted:
        return f"{name}: [REDACTED]"
    return f"{name}: {param.rendered_value}"


def _exception_type(exception: BaseException) -> str:
    return control_sanitize(type(exception).__name__)


def _render_params(node: TraceNode) -> str:
    return " ".join(_render_param(p) for p in node.signature.parameters)


def _append_trace_header(tree: TraceTree, parts: list[str]) -> None:
    """Opens in this renderer's own voice -- ``"The trace bold elk soars:"`` -- before the first
    paragraph (2026-09-13 ruling, item 4). Silent when :attr:`TraceTree.trace_id` is ``None``: an
    empty tree gets no invented name.

    This is the trace's OWN name, unrelated to the test-suite run name a caller may thread through
    a suite footer and manifest -- see :class:`~narrativetrace.output.run_identity.RunIdentity`.
    Neither ever reaches the structural ``.nt`` text.
    """
    trace_id = tree.trace_id
    if trace_id is None:
        return
    parts.append(f"The trace {trace_id.human_name()}:\n\n")


class ProseRenderer:
    """Renders a trace tree as narrative prose."""

    def render(self, tree: TraceTree) -> str:
        parts: list[str] = []
        _append_trace_header(tree, parts)
        walk = TreeWalk()
        self._render_children(tree.roots, 0, None, parts, walk)
        return "".join(parts).rstrip()

    def _render_node(
        self, node: TraceNode, depth: int, node_id: str, parts: list[str], walk: TreeWalk
    ) -> None:
        """One sentence per span, citing its span id in parentheses after the action."""
        indent = "  " * depth
        self._append_action_phrase(parts, indent, node)
        parts.append(f" ({node_id})")
        stop_reason = walk.stop_reason(node)
        if not node.children or stop_reason is not None:
            self._render_outcome_inline(node.outcome, node.signature, parts)
            if stop_reason is not None and node.children:
                parts.append(f" {stop_reason}")
            parts.append(".\n")
        else:
            walk.enter(node)
            try:
                parts.append(":\n")
                self._render_children(node.children, depth + 1, node_id, parts, walk)
                self._render_outcome_closing(node.outcome, indent, parts)
            finally:
                walk.exit(node)

    def _render_children(
        self,
        children: list[TraceNode],
        depth: int,
        parent_id: str | None,
        parts: list[str],
        walk: TreeWalk,
    ) -> None:
        """One sibling list (a tree's roots when ``parent_id`` is ``None``), each span taking its
        id in the order it is laid out."""
        ids = SpanCursor(parent_id)
        for segment in partition(children):
            if segment.group_id is None:
                self._render_node(segment.nodes[0], depth, ids.next(), parts, walk)
            elif segment.is_fire_and_forget():
                self._render_fire_and_forget(segment.nodes[0], depth, ids.next(), parts, walk)
            else:
                self._render_concurrent_group(segment.nodes, depth, ids, parts, walk)

    def _render_fire_and_forget(
        self, launcher: TraceNode, depth: int, launcher_id: str, parts: list[str], walk: TreeWalk
    ) -> None:
        """The launch, cited by its id, then the launched work; the launcher goes through the walk
        like any node, so a cycle or the depth limit ends it with the walk's marker."""
        indent = "  " * depth
        stop_reason = walk.stop_reason(launcher)
        if stop_reason is not None:
            parts.append(f"{indent}In the background ({launcher_id}) {stop_reason}.\n")
            return
        parts.append(f"{indent}In the background ({launcher_id}):\n")
        if not launcher.children:
            parts.append(f"{indent}  (launched, result not captured).\n")
            return
        walk.enter(launcher)
        try:
            self._render_children(launcher.children, depth + 1, launcher_id, parts, walk)
        finally:
            walk.exit(launcher)

    def _render_concurrent_group(
        self,
        members: list[TraceNode],
        depth: int,
        ids: SpanCursor,
        parts: list[str],
        walk: TreeWalk,
    ) -> None:
        indent = "  " * depth
        analysis = analyze(members)
        parts.append(f"{indent}Concurrently:\n")
        for member in sorted(members, key=concurrent_order):
            self._render_node(member, depth + 1, ids.next(), parts, walk)
        if analysis.is_sequential_async:
            parts.append(
                f"{indent}  (Note: tasks ran sequentially — total {analysis.total_millis}ms, "
                f"parallelizable to ~{analysis.parallelizable_millis}ms.)\n"
            )

    def _append_action_phrase(self, parts: list[str], indent: str, node: TraceNode) -> None:
        sig = node.signature
        subject = f"The {camel.to_phrase(control_sanitize(sig.class_name))}"
        action = camel.to_phrase(control_sanitize(sig.method_name))
        parts.append(f"{indent}{subject} ")
        is_error = isinstance(node.outcome, Threw | Incomplete)
        if is_error:
            parts.append("failed to ")
        parts.append(action)
        if sig.narration is not None and not is_error:
            parts.append(f" — {control_sanitize(sig.narration)}")
        else:
            params = _render_params(node)
            if params:
                parts.append(f" for {params}")

    def _render_outcome_closing(
        self, outcome: TraceOutcome | None, indent: str, parts: list[str]
    ) -> None:
        if isinstance(outcome, Returned) and outcome.rendered_value is not None:
            parts.append(f"{indent}  Returned {outcome.rendered_value}.\n")
        elif isinstance(outcome, Threw):
            message = control_sanitize(str(outcome.exception))
            parts.append(f"{indent}  {_exception_type(outcome.exception)}: {message}.\n")
        elif isinstance(outcome, Incomplete):
            parts.append(f"{indent}  ⏳ in-flight.\n")

    def _render_outcome_inline(
        self, outcome: TraceOutcome | None, sig: MethodSignature, parts: list[str]
    ) -> None:
        if isinstance(outcome, Returned) and outcome.rendered_value is not None:
            parts.append(f", returning {outcome.rendered_value}")
        elif isinstance(outcome, Threw):
            message = control_sanitize(str(outcome.exception))
            parts.append(f" — {_exception_type(outcome.exception)}: {message}")
            if sig.error_context is not None:
                parts.append(f" ({control_sanitize(sig.error_context)})")
        elif isinstance(outcome, Incomplete):
            parts.append(" — ⏳ in-flight")
