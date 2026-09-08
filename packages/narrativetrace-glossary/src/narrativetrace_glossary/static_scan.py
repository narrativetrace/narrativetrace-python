# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""No-execution glossary harvest over Python sources, via :mod:`ast`.

``GlossaryStaticScanner``. INTENT: the ``glossary-scan`` CLI (Phase 5) harvests without
running any code — a build-time scan, not a test run. This is also the *only* place narration
templates are harvested: a real trace's ``narration`` field already has values interpolated in
(``"charges $74.97"``, not ``"charges {amount}"``), so only a static read of the raw ``@narrated``/
``@on_error`` decorator argument ever sees the template text with its placeholders intact.

**Scope, matching :mod:`narrativetrace_clarity.scanner`'s own divergence**: class methods only.
The JVM has no free functions, and this runtime's ``@narrated``/``@on_error``/``trace_object``
wrapping is likewise always applied to a class's methods in practice — module-level functions are
out of scope for both scanners, for the same reason.

Unlike the dynamic harvester (:mod:`narrativetrace_glossary.harvester`), this needs no injected
``module_of`` resolver: the file's own path *is* the ground truth for its module's dotted path, so
there is nothing to infer and no ambiguity to resolve.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from narrativetrace_glossary.context_resolver import resolve_context
from narrativetrace_glossary.harvester import HarvestCandidate
from narrativetrace_glossary.models import Glossary, TermKind
from narrativetrace_glossary.normalizer import (
    class_candidate,
    method_candidates,
    parameter_candidate,
)

_IMPLICIT_PARAMS = frozenset({"self", "cls"})
_TEMPLATE_DECORATORS = frozenset({"narrated", "on_error"})
_FunctionDef = ast.FunctionDef | ast.AsyncFunctionDef
_KIND_ORDER = {kind: position for position, kind in enumerate(TermKind)}


def _is_test_file(path: Path) -> bool:
    return (
        "tests" in path.parts
        or "__pycache__" in path.parts
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


def _iter_py_files(source_root: Path) -> Iterator[Path]:
    if source_root.is_file():
        if source_root.suffix == ".py" and not _is_test_file(source_root):
            yield source_root
        return
    for path in sorted(source_root.rglob("*.py")):
        if not _is_test_file(path):
            yield path


def _module_path(file: Path, source_root: Path) -> str:
    relative = file.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _class_defs(module: ast.Module) -> list[ast.ClassDef]:
    return [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    ]


def _bound_names(module: ast.Module) -> dict[str, str]:
    """Local names bound (directly or aliased) to narrativetrace's ``narrated``/``on_error``."""
    bound: dict[str, str] = {}
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("narrativetrace"):
            for alias in node.names:
                if alias.name in _TEMPLATE_DECORATORS:
                    bound[alias.asname or alias.name] = alias.name
    return bound


def _decorator_name(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _template_argument(call: ast.Call) -> str | None:
    """The raw template text of a ``@narrated``/``@on_error`` call: its last positional string."""
    if not call.args:
        return None
    last = call.args[-1]
    return last.value if isinstance(last, ast.Constant) and isinstance(last.value, str) else None


def _harvest_templates(
    func: _FunctionDef, bound: dict[str, str], context: str, site: str
) -> Iterator[HarvestCandidate]:
    for decorator in func.decorator_list:
        name = _decorator_name(decorator)
        if name is None or bound.get(name) not in _TEMPLATE_DECORATORS:
            continue
        assert isinstance(decorator, ast.Call), "a matched decorator name is always a Call node"
        template = _template_argument(decorator)
        if template:
            yield HarvestCandidate(context, template, TermKind.TEMPLATE, site, func.name)


def _harvest_class(class_def: ast.ClassDef, context: str) -> HarvestCandidate | None:
    try:
        candidate = class_candidate(class_def.name)
    except ValueError:
        return None
    if candidate is None:
        return None
    return HarvestCandidate(
        context, candidate.phrase, candidate.kind, class_def.name, class_def.name
    )


def _param_names(func: _FunctionDef) -> list[str]:
    args = func.args
    names = [a.arg for a in (*args.posonlyargs, *args.args) if a.arg not in _IMPLICIT_PARAMS]
    names.extend(a.arg for a in args.kwonlyargs)
    return names


def _harvest_method(func: _FunctionDef, context: str, site: str) -> Iterator[HarvestCandidate]:
    try:
        candidates = method_candidates(func.name)
    except ValueError:
        return
    for candidate in candidates:
        yield HarvestCandidate(context, candidate.phrase, candidate.kind, site, func.name)


def _harvest_params(func: _FunctionDef, context: str, site: str) -> Iterator[HarvestCandidate]:
    for name in _param_names(func):
        try:
            candidate = parameter_candidate(name)
        except ValueError:
            continue
        if candidate is not None:
            yield HarvestCandidate(context, candidate.phrase, candidate.kind, site, name)


def _harvest_member(
    member: ast.stmt, context: str, class_name: str, bound: dict[str, str]
) -> Iterator[HarvestCandidate]:
    if not isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef) or member.name.startswith(
        "_"
    ):
        return
    site = f"{class_name}.{member.name}"
    yield from _harvest_method(member, context, site)
    yield from _harvest_params(member, context, site)
    yield from _harvest_templates(member, bound, context, site)


def scan_source(source: str, module_path: str, glossary: Glossary) -> tuple[HarvestCandidate, ...]:
    """Harvests one source file's text without executing it.

    Args:
        source: the file's Python source text.
        module_path: this file's dotted module path (see :func:`_module_path`), used to resolve
            the bounded context every candidate is filed under.
        glossary: supplies the bounded contexts, exactly as
            :func:`~narrativetrace_glossary.harvester.harvest_traces` does.

    Returns:
        Harvested candidates in file order; unsorted and unaggregated (:func:`scan_paths`
        aggregates and totally orders the whole run).

    A syntactically invalid file yields no candidates rather than raising — a build-time scan must
    survive one unparseable file, matching :func:`narrativetrace_clarity.scanner.scan_paths`.
    """
    try:
        module = ast.parse(source)
    except SyntaxError:
        return ()
    context = resolve_context(glossary, module_path)
    bound = _bound_names(module)
    candidates: list[HarvestCandidate] = []
    for class_def in _class_defs(module):
        own = _harvest_class(class_def, context)
        if own is not None:
            candidates.append(own)
        for member in class_def.body:
            candidates.extend(_harvest_member(member, context, class_def.name, bound))
    return tuple(candidates)


def _aggregate(raw: Iterable[HarvestCandidate]) -> tuple[HarvestCandidate, ...]:
    counts: dict[tuple[str, str, TermKind, str, str], int] = {}
    for candidate in raw:
        key = (
            candidate.context,
            candidate.phrase,
            candidate.kind,
            candidate.site,
            candidate.identifier,
        )
        counts[key] = counts.get(key, 0) + candidate.occurrences
    aggregated = (
        HarvestCandidate(context, phrase, kind, site, identifier, occurrences=count)
        for (context, phrase, kind, site, identifier), count in counts.items()
    )
    return tuple(
        sorted(
            aggregated,
            key=lambda c: (c.context, c.phrase, _KIND_ORDER[c.kind], c.site, c.identifier),
        )
    )


def scan_paths(
    source_roots: Sequence[str | Path], glossary: Glossary
) -> tuple[HarvestCandidate, ...]:
    """Harvests every ``.py`` file under the given source roots, skipping tests.

    A file is a test file (and skipped) when it sits under a ``tests``/``__pycache__`` directory
    or is named ``test_*.py``/``*_test.py`` — the same convention
    :func:`narrativetrace_clarity.scanner.scan_paths` and this repository's own test layout use.

    Returns:
        Aggregated candidates ordered by ``(context, phrase, kind, site, identifier)`` — the same
        total order :func:`~narrativetrace_glossary.harvester.harvest_traces` produces, so a
        static and a dynamic harvest of the same code merge identically.
    """
    raw: list[HarvestCandidate] = []
    for root in source_roots:
        root_path = Path(root)
        for file in _iter_py_files(root_path):
            try:
                source = file.read_text(encoding="utf-8")
            except OSError:
                continue
            raw.extend(scan_source(source, _module_path(file, root_path), glossary))
    return _aggregate(raw)
