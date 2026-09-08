# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Turns a declarative hostile-corpus trace shape (``trace-shapes.json``) into a live
``TraceTree``. The shared ``TraceShapes`` builder.

INTENT: ``hostile_graphs.py`` builds arbitrary object graphs for the value renderer; this builds
``TraceNode`` call trees specifically, for the separate walker
(:class:`narrativetrace.tree_walk.TreeWalk`) every recursive renderer and exporter shares. The
corpus stays data -- each runtime copies ``trace-shapes.json`` verbatim and writes its own builder.
"""

from __future__ import annotations

from hostile_corpus import TraceShapeCase

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

_DURATION_NANOS = 1_000_000


def _node(method_name: str, children: list[TraceNode]) -> TraceNode:
    return TraceNode(
        MethodSignature("HostileTraceShape", method_name, []),
        children,
        Returned('"ok"'),
        _DURATION_NANOS,
    )


def _chain(depth: int) -> TraceNode:
    """A linear chain ``depth`` nodes deep, innermost leaf first."""
    current = _node("leaf", [])
    for i in range(depth):
        current = _node(f"call{i}", [current])
    return current


def _ring(length: int) -> TraceNode:
    """A ring of ``length`` nodes, each holding the next; ``length == 1`` holds itself."""
    nodes = [_node(f"n{i}", []) for i in range(length)]
    for i, node in enumerate(nodes):
        node.children.append(nodes[(i + 1) % length])
    return nodes[0]


def _root(case: TraceShapeCase) -> TraceNode:
    if case.kind == "chain":
        return _chain(case.n)
    if case.kind == "cycle":
        return _ring(case.n)
    raise ValueError(f"unknown trace shape kind: {case.kind}")


def build(case: TraceShapeCase) -> TraceTree:
    """Builds the tree ``case`` describes."""
    return TraceTree([_root(case)])
