# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renderer that turns traces into short prose paragraphs.

``ProseRenderer``: ``failed to <action>`` error phrasing, parent ``:`` structure with a
closing ``Returned X.`` sentence, and ``In the background:`` / ``Concurrently:`` labels.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render import camel
from narrativetrace.render.concurrency import analyze, partition
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk


def _sig_key(node: TraceNode) -> str:
    return f"{node.signature.class_name}.{node.signature.method_name}"


def _render_param(param: ParameterCapture) -> str:
    name = control_sanitize(param.name)
    if param.redacted:
        return f"{name}: [REDACTED]"
    return f"{name}: {param.rendered_value}"


def _exception_type(exception: BaseException) -> str:
    return control_sanitize(type(exception).__name__)


def _render_params(node: TraceNode) -> str:
    return " ".join(_render_param(p) for p in node.signature.parameters)


class ProseRenderer:
    """Renders a trace tree as narrative prose."""

    def render(self, tree: TraceTree) -> str:
        parts: list[str] = []
        walk = TreeWalk()
        for root in tree.roots:
            self._render_node(root, 0, parts, walk)
        return "".join(parts).rstrip()

    def _render_node(self, node: TraceNode, depth: int, parts: list[str], walk: TreeWalk) -> None:
        indent = "  " * depth
        self._append_action_phrase(parts, indent, node)
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
                self._render_children(node.children, depth + 1, parts, walk)
                self._render_outcome_closing(node.outcome, indent, parts)
            finally:
                walk.exit(node)

    def _render_children(
        self, children: list[TraceNode], depth: int, parts: list[str], walk: TreeWalk
    ) -> None:
        for segment in partition(children):
            if segment.group_id is None:
                self._render_node(segment.nodes[0], depth, parts, walk)
            elif segment.is_fire_and_forget():
                self._render_fire_and_forget(segment.nodes[0], depth, parts, walk)
            else:
                self._render_concurrent_group(segment.nodes, depth, parts, walk)

    def _render_fire_and_forget(
        self, launcher: TraceNode, depth: int, parts: list[str], walk: TreeWalk
    ) -> None:
        indent = "  " * depth
        parts.append(f"{indent}In the background:\n")
        if not launcher.children:
            parts.append(f"{indent}  (launched, result not captured).\n")
        else:
            for child in launcher.children:
                self._render_node(child, depth + 1, parts, walk)

    def _render_concurrent_group(
        self, members: list[TraceNode], depth: int, parts: list[str], walk: TreeWalk
    ) -> None:
        indent = "  " * depth
        analysis = analyze(members)
        parts.append(f"{indent}Concurrently:\n")
        for member in sorted(members, key=_sig_key):
            self._render_node(member, depth + 1, parts, walk)
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
