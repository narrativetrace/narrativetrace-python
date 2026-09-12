# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders the AI-safe structural trace artifact (ADR-002): the developer-authored shape of a
scenario with zero runtime values.

``StructuralTraceRenderer``. One artifact per test scenario (``.nt``) containing only code
structure — class, method and parameter *names*, the call hierarchy, and outcome *kinds*. No
argument or return values, no exception messages, no durations, no timestamps, no trace
identifiers. Zero runtime values means zero prompt-injection surface and zero PII, and the output
is deterministic byte-for-byte for identical behavior — the property that makes it the
approval-testing baseline (``.approved.nt``) and the cross-platform conformance-fixture format.

This is projection-last by construction: the renderer reads the same :class:`TraceTree` every
other renderer reads and elides values at render time — nothing about a call's *shape* is captured
or tracked separately from the full-detail capture. Byte-identical to the reference format: the
grammar, the two-space indent, the outcome-kind markers, and the ``~ fork``/``~ async``/
``~ fire-and-forget`` concurrency markers are a cross-platform contract, not a rendering choice
this port made independently — see ``documentation/structural-trace-format.md``.

Every walk goes through :class:`~narrativetrace.tree_walk.TreeWalk`: a hand-built, replayed or
deserialized tree is not guaranteed acyclic (``TraceNode.children`` is an undefended list), and a
genuinely deep tree is ordinary for a recursive business method. A node beyond ``MAX_DEPTH`` or
already on the current path still gets its own line, with the walk's marker appended — the walk
simply never descends into its children.
"""

from __future__ import annotations

from narrativetrace.concurrency import ConcurrencyKind
from narrativetrace.escape import control_sanitize
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.concurrency import ChildSegment, partition
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk


def _sig_key(node: TraceNode) -> str:
    return f"{node.signature.class_name}.{node.signature.method_name}"


def _outcome_kind(outcome: TraceOutcome | None) -> str:
    if isinstance(outcome, Returned) and outcome.rendered_value is not None:
        return " → value"
    if isinstance(outcome, Threw):
        return f" !! {control_sanitize(type(outcome.exception).__name__)}"
    if isinstance(outcome, Incomplete):
        return " ?? incomplete"
    return ""


class StructuralTraceRenderer:
    """Renders a :class:`TraceTree` into the value-free ``.nt`` structural format."""

    def render_document(self, tree: TraceTree, scenario: str) -> str:
        """The full artifact: a ``scenario:`` header (stable across runs) plus the call flow.

        Nothing else — no result, no ids, no dates — so the file changes only when behavior does.
        """
        return f"scenario: {control_sanitize(scenario)}\n\n{self.render(tree)}"

    def render(self, tree: TraceTree) -> str:
        """The call-flow body alone (no header) — roots go through the same partitioning as
        children: async work that outlived its caller is a root, and its order is the scheduler's,
        not the code's."""
        parts: list[str] = []
        walk = TreeWalk()
        self._render_siblings(tree.roots, 0, walk, parts)
        return "".join(parts)

    def _render_siblings(
        self, children: list[TraceNode], depth: int, walk: TreeWalk, parts: list[str]
    ) -> None:
        for segment in partition(children):
            if segment.group_id is None:
                self._render_node(segment.nodes[0], depth, walk, parts)
            elif segment.is_fire_and_forget():
                self._render_fire_and_forget(segment.nodes[0], depth, walk, parts)
            else:
                self._render_group(segment, depth, walk, parts)

    def _render_node(self, node: TraceNode, depth: int, walk: TreeWalk, parts: list[str]) -> None:
        stop_reason = walk.stop_reason(node)
        marker = stop_reason if stop_reason is not None and node.children else None
        parts.append(self._line(node, depth, marker))
        if node.children and stop_reason is None:
            walk.enter(node)
            try:
                self._render_siblings(node.children, depth + 1, walk, parts)
            finally:
                walk.exit(node)

    def _line(self, node: TraceNode, depth: int, marker: str | None) -> str:
        sig = node.signature
        params = ", ".join(control_sanitize(p.name) for p in sig.parameters)
        line = (
            f"{'  ' * depth}- {control_sanitize(sig.class_name)}."
            f"{control_sanitize(sig.method_name)}({params})"
        )
        line += _outcome_kind(node.outcome)
        if marker is not None:
            line += f" {marker}"
        return line + "\n"

    def _render_fire_and_forget(
        self, launcher: TraceNode, depth: int, walk: TreeWalk, parts: list[str]
    ) -> None:
        parts.append(f"{'  ' * depth}~ fire-and-forget\n")
        self._render_siblings(launcher.children, depth + 1, walk, parts)

    def _render_group(
        self, segment: ChildSegment, depth: int, walk: TreeWalk, parts: list[str]
    ) -> None:
        """Concurrent groups render under a marker (``~ fork [n]``, ``~ async [n]``) with members
        sorted by signature — capture order across threads is the scheduler's choice, not
        behaviour, and this artifact must be byte-identical for identical behavior. Thread
        identity is runtime data and never appears."""
        members = segment.nodes
        first_concurrency = members[0].concurrency
        marker = (
            "~ async"
            if first_concurrency is not None and first_concurrency.kind is ConcurrencyKind.ASYNC
            else "~ fork"
        )
        parts.append(f"{'  ' * depth}{marker} [{len(members)}]\n")
        for member in sorted(members, key=_sig_key):
            self._render_node(member, depth + 1, walk, parts)
