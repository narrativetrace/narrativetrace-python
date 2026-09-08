# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Bounded, cycle-safe recursion guard for :class:`~narrativetrace.nodes.TraceNode` tree walks.

The ``TreeWalk`` semantics (bounded depth,
identity-based cycle detection) at Python's own recursion scale. ``TraceNode.children`` is a plain
mutable list even under ``frozen=True``, so a hand-built, replayed, or deserialized tree can be
genuinely cyclic, and a merely deep tree (a recursive business method) is ordinary. Before this
module existed, every recursive renderer/exporter walking a trace tree here used unbounded
native recursion with no depth bound or cycle guard -- both a cycle and a sufficiently deep chain
crashed with an uncaught ``RecursionError``, Python's analogue of Java's ``StackOverflowError``.

This runtime keeps native recursion at each call site (mirrors ``rendering.ValueRenderer``'s
identical, already-reviewed ``_RenderWalk`` pattern for arbitrary value graphs) rather than
rewriting every walker as an explicit-stack iterator, so ``MAX_DEPTH`` is picked far below Python's
own recursion ceiling instead of matching Java's 10,000 literally. Measured empirically
(2026-09-04): the most stack-frame-hungry walker in this runtime (``MarkdownRenderer``'s mutual
recursion) overflows Python's default 1,000-frame recursion limit at a 332-node chain;
``MAX_DEPTH`` leaves more than 3x headroom there, and far more for every cheaper (fewer-frames-
per-level) walker -- confirmed safe even under an artificially reduced ``recursionlimit`` of 400,
simulating a busier ambient call stack (e.g. inside a web framework or async runtime).
"""

from __future__ import annotations

MAX_DEPTH = 100

DEPTH_LIMIT_MARKER = "… (depth limit)"
CYCLE_MARKER = "… (cycle)"


class TreeWalk:
    """One traversal's recursion state: identity ancestry plus remaining depth budget.

    "Have I been here before" (a cycle) and "how deep am I" (the depth bound) are different
    questions answered together because both unwind in the same ``finally`` a caller wraps around
    its recursive descent into one node's children.
    """

    __slots__ = ("_ancestors", "_depth")

    def __init__(self) -> None:
        self._ancestors: set[int] = set()
        self._depth = 0

    def stop_reason(self, node: object) -> str | None:
        """Why ``node`` must not be descended into, or ``None`` to proceed.

        Checked *before* entering a node, so the node itself still renders/counts even when
        stopped -- only its children are never visited. A node already an ancestor on the current
        path (a cycle) is reported before a node merely at the depth cap, since the two can
        coincide and a cycle is the more specific diagnosis.
        """
        if id(node) in self._ancestors:
            return CYCLE_MARKER
        if self._depth >= MAX_DEPTH:
            return DEPTH_LIMIT_MARKER
        return None

    def enter(self, node: object) -> None:
        """Marks ``node`` as an ancestor of whatever is visited next, and claims one level of
        depth budget."""
        self._ancestors.add(id(node))
        self._depth += 1

    def exit(self, node: object) -> None:
        """Un-marks ``node`` and returns its depth budget once its subtree has finished."""
        self._ancestors.discard(id(node))
        self._depth -= 1
