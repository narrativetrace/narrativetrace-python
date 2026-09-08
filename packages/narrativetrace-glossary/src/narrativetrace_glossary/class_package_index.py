# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Builds a ``class_name -> module path`` lookup from already-captured trace trees.

``ClassPackageIndex`` (Java's compiled-class-directory scan, .NET's loaded-assembly
scan). INTENT: :func:`~narrativetrace_glossary.harvester.harvest_traces` takes a ``module_of``
callable but does not build one itself — every runtime resolves it differently. Here, the resolver
that matters is trivial: :attr:`~narrativetrace.signature.MethodSignature.package_name` is already
captured on every node (``__module__`` at trace time), so this only needs to aggregate it and
resolve ambiguity, never scan anything.

**Do not default this to "always None".** A prior mirror (dotnet, audit finding G1a) shipped a
suite reporter that passed a namespace resolver returning ``None`` unconditionally, so every
harvested term landed in ``_unassigned`` and every bounded context a project declared was
decoration. Ambiguity is resolved to ``None`` deliberately (a class name seen under two different
modules names no single context); *absence of any observation* must never be confused with that —
it is also ``None``, but for the ordinary reason that harvesting only ever sees the classes a run
actually touched.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk


def _walk(tree_roots: Sequence[object], observed: dict[str, set[str | None]]) -> None:
    walk = TreeWalk()
    _walk_nodes(tree_roots, observed, walk)


def _walk_nodes(
    nodes: Sequence[object], observed: dict[str, set[str | None]], walk: TreeWalk
) -> None:
    for node in nodes:
        signature = node.signature  # type: ignore[attr-defined]
        observed.setdefault(signature.class_name, set()).add(signature.package_name)
        if walk.stop_reason(node) is None:
            walk.enter(node)
            try:
                _walk_nodes(node.children, observed, walk)  # type: ignore[attr-defined]
            finally:
                walk.exit(node)


def class_package_index(trees: Sequence[TraceTree]) -> Callable[[str], str | None]:
    """Builds a ``module_of`` resolver from the ``package_name`` every node already carries.

    A class name observed under exactly one non-``None`` module resolves to it; observed under two
    or more distinct modules (or never observed, or only ever observed without a captured module)
    resolves to ``None`` — files that class's terms under ``_unassigned`` rather than guessing.

    Returns:
        A callable suitable as :func:`~narrativetrace_glossary.harvester.harvest_traces`'s
        ``module_of`` argument.
    """
    observed: dict[str, set[str | None]] = {}
    for tree in trees:
        _walk(tree.roots, observed)
    resolved = {
        class_name: next(iter(modules))
        for class_name, modules in observed.items()
        if len(modules) == 1 and next(iter(modules)) is not None
    }
    return resolved.get
