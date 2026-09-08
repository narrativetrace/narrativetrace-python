# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""YAML frontmatter for Markdown trace documents.

``FrontmatterBuilder``.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Threw
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk

_YAML_INDICATOR_LEADERS = frozenset("-?:,[]{}#&*!|>'\"%@`")
"""Characters a YAML plain scalar cannot start with (security fuzz suite finding: an unquoted
scenario starting with e.g. ``%`` is not a directive, it is a scalar, but the reader cannot tell
without a quote)."""

_YAML_NONCHARACTERS = chr(0xFFFE) + chr(0xFFFF)
"""The two BMP noncharacters YAML's own printable-character rule excludes from its otherwise
unrestricted private-use range (``U+E000``-``U+FFFD``) -- outside ``control_sanitize``'s
definition of a control character, since they are not one, but still not raw-YAML-safe."""


def yaml_safe(value: str) -> str:
    """Quotes/escapes a scenario value that would otherwise break or be misread as YAML."""
    if _needs_quoting(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = control_sanitize(escaped)
        escaped = "".join(f"\\u{ord(c):04x}" if c in _YAML_NONCHARACTERS else c for c in escaped)
        escaped = _escape_supplementary(escaped)
        return f'"{escaped}"'
    return value


def _escape_supplementary(text: str) -> str:
    """Every code point above the Basic Multilingual Plane becomes an 8-digit ``\\U`` escape.

    A Python ``str`` already holds a supplementary character as one code point, and PyYAML
    round-trips it raw without incident -- unlike Java's UTF-16-backed ``String``, there is no
    surrogate-pair encoding here for a downstream reader's buffer boundary to split. But
    frontmatter is a machine-readable interoperability contract this runtime shares with every
    other NarrativeTrace runtime (mirrors the Java spec repo's fix for its SnakeYAML 2.3 crash,
    a 2026-09-08 audit's finding), so it is kept BMP-only here too: ``\\U`` is YAML's own
    32-bit escape (``ns-esc-32-bit``), and a conforming parser anywhere decodes it back to the
    same code point.
    """
    return "".join(f"\\U{ord(c):08x}" if ord(c) > 0xFFFF else c for c in text)


def _needs_quoting(value: str) -> bool:
    if not value or value != value.strip() or value[0] in _YAML_INDICATOR_LEADERS:
        return True
    if any(c in value for c in ':#"\\\n'):
        return True
    if any(c in _YAML_NONCHARACTERS for c in value):
        return True
    if any(ord(c) > 0xFFFF for c in value):
        return True
    # control_sanitize is a no-op on a string with no control character or surrogate to escape --
    # reusing it here means "does this need a \n/\uXXXX escape" never drifts from the one place
    # that defines what a control character is.
    return control_sanitize(value) != value


def _count_nodes(node: TraceNode, walk: TreeWalk | None = None) -> int:
    walk = walk if walk is not None else TreeWalk()
    total = 1
    if walk.stop_reason(node) is None:
        walk.enter(node)
        try:
            total += sum(_count_nodes(child, walk) for child in node.children)
        finally:
            walk.exit(node)
    return total


def _count_errors(node: TraceNode, walk: TreeWalk | None = None) -> int:
    walk = walk if walk is not None else TreeWalk()
    own = 1 if isinstance(node.outcome, Threw) else 0
    if walk.stop_reason(node) is None:
        walk.enter(node)
        try:
            own += sum(_count_errors(child, walk) for child in node.children)
        finally:
            walk.exit(node)
    return own


class FrontmatterBuilder:
    """Builds the YAML frontmatter block for a trace document."""

    def __init__(self) -> None:
        self._scenario: str | None = None

    def scenario(self, scenario: str) -> FrontmatterBuilder:
        """Sets the scenario line; returns self for chaining."""
        self._scenario = scenario
        return self

    def build(self, tree: TraceTree) -> str:
        """Renders the frontmatter block (delimited by ``---`` lines)."""
        lines = ["---", "type: trace"]
        if self._scenario is not None:
            lines.append(f"scenario: {yaml_safe(self._scenario)}")
        if tree.roots:
            root = tree.roots[0]
            sig = root.signature
            entry_point = f"{sig.class_name}.{sig.method_name}"
            lines.append(f"entry_point: {yaml_safe(entry_point)}")
            lines.append(f"duration_ms: {root.duration_millis}")
            if root.span_context is not None:
                trace_id = root.span_context.trace_id
                lines.append(f"trace_id: {trace_id}")
                lines.append(f"trace_name: {trace_id.human_name()}")
        method_count = sum(_count_nodes(root) for root in tree.roots)
        error_count = sum(_count_errors(root) for root in tree.roots)
        lines.append(f"method_count: {method_count}")
        lines.append(f"error_count: {error_count}")
        lines.append("---")
        return "\n".join(lines) + "\n"
