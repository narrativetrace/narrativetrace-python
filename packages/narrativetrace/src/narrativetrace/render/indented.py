# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Plain-text renderer using tree indentation and arrow notation.

``IndentedTextRenderer`` — the console/pytest-failure renderer. Errors render as
``!! Type: message | error_context``; redacted params as ``[REDACTED]``; narration as ``// ...``.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.concurrency import analyze, partition
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


def _sig_key(node: TraceNode) -> str:
    return f"{node.signature.class_name}.{node.signature.method_name}"


class IndentedTextRenderer:
    """Renders a trace tree as an indented ASCII tree."""

    def render(self, tree: TraceTree) -> str:
        parts: list[str] = []
        walk = TreeWalk()
        for root in tree.roots:
            self._render_node(root, "", "", parts, walk)
        return "".join(parts).rstrip()

    def _render_node(
        self, node: TraceNode, line_prefix: str, cont_prefix: str, parts: list[str], walk: TreeWalk
    ) -> None:
        stop_reason = walk.stop_reason(node)
        if not node.children or stop_reason is not None:
            self._render_leaf_node(node, line_prefix, stop_reason, parts)
        else:
            self._render_branch_node(node, line_prefix, cont_prefix, parts, walk)

    def _render_leaf_node(
        self, node: TraceNode, line_prefix: str, stop_reason: str | None, parts: list[str]
    ) -> None:
        """A node with no children, or one whose children the walk stopped short of visiting --
        the node still contributes its own header/outcome, only its subtree is cut off."""
        sig = node.signature
        parts.append(f"{line_prefix}{_header(sig)}")
        self._render_outcome_inline(node.outcome, sig, parts)
        self._render_duration(node, parts)
        if stop_reason is not None and node.children:
            parts.append(f" {stop_reason}")
        parts.append("\n")

    def _render_branch_node(
        self,
        node: TraceNode,
        line_prefix: str,
        cont_prefix: str,
        parts: list[str],
        walk: TreeWalk,
    ) -> None:
        walk.enter(node)
        try:
            sig = node.signature
            parts.append(f"{line_prefix}{_header(sig)}\n")
            self._render_narration(sig, cont_prefix, parts)
            self._render_children(node.children, cont_prefix, parts, walk)
            parts.append(f"{cont_prefix}└── ")
            self._render_outcome_closing(node.outcome, sig, parts)
            self._render_duration(node, parts)
            parts.append("\n")
        finally:
            walk.exit(node)

    def _render_children(
        self, children: list[TraceNode], cont_prefix: str, parts: list[str], walk: TreeWalk
    ) -> None:
        for segment in partition(children):
            if segment.group_id is None:
                self._render_node(
                    segment.nodes[0], f"{cont_prefix}├── ", f"{cont_prefix}│   ", parts, walk
                )
            elif segment.is_fire_and_forget():
                self._render_fire_and_forget(segment.nodes[0], cont_prefix, parts, walk)
            else:
                self._render_concurrent_group(segment.nodes, cont_prefix, parts, walk)

    def _render_fire_and_forget(
        self, launcher: TraceNode, cont_prefix: str, parts: list[str], walk: TreeWalk
    ) -> None:
        parts.append(f"{cont_prefix}├── ⤳ fire-and-forget")
        if launcher.concurrency is not None:
            parts.append(f" [thread: {_thread_label(launcher)}]")
        parts.append("\n")
        if not launcher.children:
            parts.append(f"{cont_prefix}│       [launched, result not captured]\n")
        else:
            for child in launcher.children:
                self._render_node(
                    child, f"{cont_prefix}│   ├── ", f"{cont_prefix}│   │   ", parts, walk
                )

    def _render_concurrent_group(
        self, members: list[TraceNode], cont_prefix: str, parts: list[str], walk: TreeWalk
    ) -> None:
        analysis = analyze(members)
        parts.append(f"{cont_prefix}├── ⑂ fork [{len(members)} tasks]\n")
        for member in sorted(members, key=_sig_key):
            self._render_concurrent_member(
                member, f"{cont_prefix}│   ", analysis.is_sequential_async, parts, walk
            )
        wall_ms = max((m.duration_nanos for m in members), default=0) // _NANOS_PER_MILLI
        parts.append(f"{cont_prefix}├── ⑃ join — {wall_ms}ms\n")
        if analysis.is_sequential_async:
            parts.append(
                f"{cont_prefix}├── ⚡ Sequential async: total {analysis.total_millis}ms, "
                f"parallelizable to ~{analysis.parallelizable_millis}ms\n"
            )

    def _render_concurrent_member(
        self,
        node: TraceNode,
        cont_prefix: str,
        sequential_async: bool,
        parts: list[str],
        walk: TreeWalk,
    ) -> None:
        sig = node.signature
        parts.append(f"{cont_prefix}├── ↦ {_header(sig)}")
        self._render_outcome_inline(node.outcome, sig, parts)
        self._render_duration(node, parts)
        parts.append("\n")
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
