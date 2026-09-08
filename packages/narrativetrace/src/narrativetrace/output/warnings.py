# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Detects unresolved annotation placeholders that survived template resolution.

``TemplateWarningCollector``. Scans both ``narration`` and ``error_context`` of every
node for unresolved ``{token}`` placeholders (permissive ``\\{[^}]+\\}`` regex).
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.nodes import TraceNode
from narrativetrace.template import find_unresolved
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk


@dataclass(frozen=True, slots=True)
class TemplateWarning:
    """One unresolved placeholder found on a node's narration or error context."""

    class_name: str
    method_name: str
    placeholder: str
    field: str


def _collect_from_node(
    node: TraceNode, warnings: list[TemplateWarning], walk: TreeWalk | None = None
) -> None:
    walk = walk if walk is not None else TreeWalk()
    sig = node.signature
    for placeholder in find_unresolved(sig.narration):
        warnings.append(TemplateWarning(sig.class_name, sig.method_name, placeholder, "narration"))
    for placeholder in find_unresolved(sig.error_context):
        warnings.append(
            TemplateWarning(sig.class_name, sig.method_name, placeholder, "errorContext")
        )
    if walk.stop_reason(node) is None:
        walk.enter(node)
        try:
            for child in node.children:
                _collect_from_node(child, warnings, walk)
        finally:
            walk.exit(node)


def collect(trace: TraceTree) -> list[TemplateWarning]:
    """Returns every unresolved-placeholder warning in the tree."""
    warnings: list[TemplateWarning] = []
    for root in trace.roots:
        _collect_from_node(root, warnings)
    return warnings


def format_warnings(warnings: list[TemplateWarning]) -> str:
    """Formats warnings under a shared header (empty string when there are none)."""
    if not warnings:
        return ""
    lines = ["WARNING: Unresolved template placeholder(s) detected:"]
    lines.extend(
        f"  - {w.class_name}.{w.method_name}: {{{w.placeholder}}} in {w.field}" for w in warnings
    )
    return "\n".join(lines) + "\n"
