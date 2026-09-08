# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Static clarity scanner over Python sources via :mod:`ast`.

The Python form of the reflection-based ``ClarityScanner``: instead of loading compiled
classes, it parses ``.py`` sources and, for each class, builds a synthetic one-level trace tree
whose roots are the class's public methods (each a depth-1 node carrying that method's parameters,
``self``/``cls`` excluded). Results are keyed by class name. Unparseable files are skipped rather
than failing the whole scan, mirroring Java's "skip unloadable classes" behaviour.

**Documented divergence:** Java is class-only (the JVM has no free functions); this scanner scores
classes for parity. Module-level functions have no Java counterpart and are not scored.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace_clarity.analyzer import analyze
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from narrativetrace_clarity.models import ClarityResult

_IMPLICIT_PARAMS = frozenset({"self", "cls"})
_FunctionDef = ast.FunctionDef | ast.AsyncFunctionDef


def scan_source(
    source: str, filename: str = "<unknown>", vocabulary: DomainVocabulary = EMPTY
) -> dict[str, ClarityResult]:
    """Parses one Python source string and scores each class it defines.

    ``vocabulary`` is the project's committed glossary vocabulary, so a scan speaks the same
    language as a test run of the same repository.
    """
    module = ast.parse(source, filename)
    results: dict[str, ClarityResult] = {}
    for class_def in _class_defs(module):
        nodes = _build_nodes(class_def)
        if nodes:
            results[class_def.name] = analyze(TraceTree(nodes), vocabulary)
    return results


def scan_paths(
    paths: Iterable[str | Path], vocabulary: DomainVocabulary = EMPTY
) -> dict[str, ClarityResult]:
    """Scans every ``.py`` file under the given files/directories, keyed by class name."""
    results: dict[str, ClarityResult] = {}
    for path in _iter_py_files(paths):
        try:
            source = path.read_text(encoding="utf-8")
            results.update(scan_source(source, str(path), vocabulary))
        except (SyntaxError, OSError, ValueError):
            continue
    return results


def _class_defs(module: ast.Module) -> list[ast.ClassDef]:
    # Java scans public classes only; the Python analogue skips underscore-prefixed classes.
    return [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    ]


def _build_nodes(class_def: ast.ClassDef) -> list[TraceNode]:
    nodes: list[TraceNode] = []
    for member in class_def.body:
        if isinstance(member, _FunctionDef) and not member.name.startswith("_"):
            signature = MethodSignature(class_def.name, member.name, _build_params(member))
            nodes.append(TraceNode(signature, [], Returned("")))
    return nodes


def _build_params(func: _FunctionDef) -> list[ParameterCapture]:
    args = func.args
    names = [a.arg for a in (*args.posonlyargs, *args.args)]
    names = [n for n in names if n not in _IMPLICIT_PARAMS]
    names.extend(a.arg for a in args.kwonlyargs)
    return [ParameterCapture(name, "") for name in names]


def _iter_py_files(paths: Iterable[str | Path]) -> Iterator[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            yield from sorted(path.rglob("*.py"))
        elif path.suffix == ".py":
            yield path
