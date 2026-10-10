# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What in a project's Python source proves a framework row's wiring was applied — the evidence a
:class:`~narrativetrace_tooling.frameworks.table.Snippet` row carries.

INTENT: Java matches patterns over text because a Java project's wiring is often in YAML or
properties; every Python row's wiring is Python, so this reads it with :mod:`ast` instead. That is
what keeps an import (``from narrativetrace_asgi import NarrativeTraceMiddleware``), a comment or a
docstring naming the thing from counting as having USED it — the "imported, never applied" shape
the doctor exists to catch — and it needs no pattern a ReDoS gate would have to vet.

**@llmNote** A file that does not parse (a syntax error, a NUL byte, nesting deep enough to exhaust
the parser) is no evidence and never a crash. One parse per distinct file text, cached and bounded:
every row's check reads the same files.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Final, Protocol

_FIXTURE_REQUEST_CALLS: Final = frozenset({"usefixtures", "getfixturevalue"})
_PARSED_FILES_CACHED: Final = 256
_TEST_DIRECTORIES: Final = frozenset({"tests", "test"})


def is_test_source(path: str) -> bool:
    """Whether a relative path is a test module by pytest's own conventions: ``test_*.py``,
    ``*_test.py`` or ``conftest.py``, or any file under a ``tests``/``test`` directory — matched by
    directory SEGMENT, never by substring (``contest/``, ``latest/`` are not test directories)."""
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    by_name = name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py")
    return by_name or not _TEST_DIRECTORIES.isdisjoint(parts[:-1])


class Evidence(Protocol):
    """One thing whose presence in a Python source file shows a row's wiring applied."""

    def found_in(self, source: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class UsesName:
    """``name`` used in code — called, passed, subclassed or reached as an attribute, under its own
    name or an ``import … as`` alias — anywhere but an import statement, a comment, a string, a
    type annotation, or the left-hand side of an assignment."""

    name: str

    def found_in(self, source: str) -> bool:
        if self.name not in source:
            return False
        facts = _facts(source)
        names = {self.name} | {alias for alias, original in facts.aliases if original == self.name}
        return not names.isdisjoint(facts.used_names)


@dataclass(frozen=True, slots=True)
class RequestsFixture:
    """A pytest fixture requested by ``name``: a function parameter, or the string a
    ``usefixtures(...)``/``getfixturevalue(...)`` call names."""

    name: str

    def found_in(self, source: str) -> bool:
        if self.name not in source:
            return False
        facts = _facts(source)
        return self.name in facts.parameters or self.name in facts.fixture_requests


@dataclass(frozen=True, slots=True)
class _Facts:
    used_names: frozenset[str]
    parameters: frozenset[str]
    fixture_requests: frozenset[str]
    aliases: frozenset[tuple[str, str]]
    """``(alias, imported name)`` for every ``import … as alias``."""


_NOTHING: Final = _Facts(frozenset(), frozenset(), frozenset(), frozenset())


@lru_cache(maxsize=_PARSED_FILES_CACHED)
def _facts(source: str) -> _Facts:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return _NOTHING
    used: set[str] = set()
    parameters: set[str] = set()
    requests: set[str] = set()
    aliases: set[tuple[str, str]] = set()
    for node in _outside_annotations(tree):
        _collect_use(node, used)
        if isinstance(node, ast.arg):
            parameters.add(node.arg)
        elif isinstance(node, ast.Call):
            requests.update(_fixture_requests(node))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            aliases.update((a.asname, a.name.rsplit(".", 1)[-1]) for a in node.names if a.asname)
    return _Facts(frozenset(used), frozenset(parameters), frozenset(requests), frozenset(aliases))


def _outside_annotations(tree: ast.AST) -> Iterator[ast.AST]:
    """Every node except those inside a type annotation — a parameter's, a return's or an annotated
    assignment's: naming a type is not applying it. Iterative, like :func:`ast.walk`."""
    pending: list[ast.AST] = [tree]
    while pending:
        node = pending.pop()
        yield node
        skipped = _annotation_of(node)
        pending.extend(child for child in ast.iter_child_nodes(node) if child is not skipped)


def _annotation_of(node: ast.AST) -> ast.AST | None:
    if isinstance(node, (ast.arg, ast.AnnAssign)):
        return node.annotation
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.returns
    return None


def _collect_use(node: ast.AST, used: set[str]) -> None:
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        used.add(node.id)
    elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
        used.add(node.attr)


def _fixture_requests(call: ast.Call) -> list[str]:
    function = call.func
    name = function.attr if isinstance(function, ast.Attribute) else getattr(function, "id", None)
    if name not in _FIXTURE_REQUEST_CALLS:
        return []
    return [
        arg.value
        for arg in call.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    ]
