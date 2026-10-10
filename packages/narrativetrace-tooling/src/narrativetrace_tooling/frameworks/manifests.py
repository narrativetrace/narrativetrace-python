# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Which distributions a project DECLARES — the framework table's marker and reference columns read
this, never an install and never a lockfile.

INTENT: the doctor measures a project against the framework table from text alone (Phase 6 D3: no
build execution, no import of the project), so "the project uses FastAPI" means "a manifest the
project wrote names ``fastapi``". Manifests are read the way people write them: every
``pyproject.toml`` in the walk (PEP 621 dependencies and extras, PEP 735 dependency groups, uv's
``dev-dependencies``, Poetry's tables), ``requirements*.txt`` (also under a ``requirements/``
directory), ``setup.cfg``, ``setup.py`` and ``Pipfile``. A lockfile is deliberately absent: it names
what something ELSE pulled in, which proves nothing about what the project itself uses.

**@llmNote** Every reader is total — a file that does not parse, or a table of the wrong shape,
declares nothing rather than raising, because one broken manifest must not take the whole doctor
run down. Names are compared PEP 503-normalized (:func:`normalize`).
"""

from __future__ import annotations

import ast
import configparser
import re
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from typing import Final

_SEPARATORS: Final = re.compile(r"[-_.]+")
_REQUIREMENT_NAME: Final = re.compile(r"\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")
_SETUP_PY_KEYWORDS: Final = frozenset({"install_requires", "extras_require", "tests_require"})
_POETRY_SKIPPED: Final = frozenset({"python"})
_MANIFEST_NAMES: Final = frozenset({"pyproject.toml", "Pipfile", "setup.cfg", "setup.py"})
_BYTE_ORDER_MARK: Final = "\ufeff"
_REQUIREMENTS_STEM: Final = re.compile(r"(?:^|[-_.])requirements(?:[-_.]|$)")
_REQUIREMENTS_SUFFIXES: Final = (".txt", ".in")


def normalize(name: str) -> str:
    """``name`` as PEP 503 compares distribution names: lower case, separator runs as one dash."""
    return _SEPARATORS.sub("-", name).lower()


def declared_distributions(files: Mapping[str, str]) -> frozenset[str]:
    """Every distribution any manifest among ``files`` (relative path -> text) declares,
    normalized."""
    names: set[str] = set()
    for path, text in files.items():
        names.update(_declared_in(path, text.removeprefix(_BYTE_ORDER_MARK)))
    return frozenset(normalize(name) for name in names)


def is_manifest(path: str) -> bool:
    """Whether a relative path names a file this module reads — the doctor's walker keeps exactly
    these beside the source it already reads, whatever their suffix."""
    parts = _segments(path)
    return parts[-1] in _MANIFEST_NAMES or _is_requirements_file(parts)


def _segments(path: str) -> list[str]:
    return path.replace("\\", "/").split("/")


def _declared_in(path: str, text: str) -> Iterator[str]:
    parts = _segments(path)
    name = parts[-1]
    if name in ("pyproject.toml", "Pipfile"):
        table = _toml(text)
        reader = _pyproject_requirements if name == "pyproject.toml" else _pipfile_requirements
        yield from reader(table)
    elif _is_requirements_file(parts):
        yield from _requirement_names(text.splitlines())
    elif name == "setup.cfg":
        yield from _setup_cfg_requirements(text)
    elif name == "setup.py":
        yield from _setup_py_requirements(text)


def _is_requirements_file(parts: list[str]) -> bool:
    """A ``.txt`` (pip) or ``.in`` (pip-tools' source) file whose name has ``requirements`` as one
    of its ``-``/``_``/``.``-separated words (``requirements.txt``, ``requirements-dev.txt``,
    ``dev-requirements.txt``, ``requirements.in``), or any such file directly under a
    ``requirements/`` directory — matched by word and directory SEGMENT, never by substring."""
    name = parts[-1]
    if not name.endswith(_REQUIREMENTS_SUFFIXES):
        return False
    stem = name.rsplit(".", 1)[0]
    in_directory = len(parts) > 1 and parts[-2] == "requirements"
    return in_directory or _REQUIREMENTS_STEM.search(stem) is not None


def _toml(text: str) -> Mapping[str, object]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}


def _table(parent: Mapping[str, object], *keys: str) -> Mapping[str, object]:
    """The nested table at ``keys``, or empty when any step is missing or not a table."""
    node: object = parent
    for key in keys:
        node = node.get(key) if isinstance(node, Mapping) else None
    return node if isinstance(node, Mapping) else {}


def _strings(value: object) -> list[str]:
    """The string items of a TOML array; anything else (an include-group table, a bare string
    where an array belongs) contributes nothing."""
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _pyproject_requirements(doc: Mapping[str, object]) -> Iterator[str]:
    project = _table(doc, "project")
    specs = _strings(project.get("dependencies"))
    for group in (_table(project, "optional-dependencies"), _table(doc, "dependency-groups")):
        for value in group.values():
            specs.extend(_strings(value))
    specs.extend(_strings(_table(doc, "tool", "uv").get("dev-dependencies")))
    yield from _requirement_names(specs)
    yield from _poetry_names(_table(doc, "tool", "poetry"))


def _poetry_names(poetry: Mapping[str, object]) -> Iterator[str]:
    tables = [_table(poetry, "dependencies"), _table(poetry, "dev-dependencies")]
    tables.extend(
        _table(group, "dependencies")
        for group in _table(poetry, "group").values()
        if isinstance(group, Mapping)
    )
    for table in tables:
        yield from (name for name in table if name.lower() not in _POETRY_SKIPPED)


def _pipfile_requirements(doc: Mapping[str, object]) -> Iterator[str]:
    yield from _table(doc, "packages")
    yield from _table(doc, "dev-packages")


def _requirement_names(lines: Iterable[str]) -> Iterator[str]:
    """The distribution name each PEP 508 line starts with; comments, blank lines and pip options
    (``-r``, ``-e``, ``--index-url``) name none."""
    for line in lines:
        content = line.split("#", 1)[0].strip()
        if not content or content.startswith("-"):
            continue
        match = _REQUIREMENT_NAME.match(content)
        if match is not None:
            yield match.group(1)


def _setup_cfg_requirements(text: str) -> Iterator[str]:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error:
        return
    if parser.has_option("options", "install_requires"):
        yield from _requirement_names(parser.get("options", "install_requires").splitlines())
    if parser.has_section("options.extras_require"):
        for _, value in parser.items("options.extras_require"):
            yield from _requirement_names(value.splitlines())


def _setup_py_requirements(text: str) -> Iterator[str]:
    """String literals under ``setup()``'s requirement keywords — written inline, or bound to a
    module-level name first (``REQUIRES = [...]``, ``install_requires=REQUIRES``) — read with
    :mod:`ast`: the file is never executed."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return
    bound = _module_level_bindings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in _SETUP_PY_KEYWORDS:
            value = (
                bound.get(node.value.id, node.value)
                if isinstance(node.value, ast.Name)
                else node.value
            )
            yield from _requirement_names(_string_constants(value))


def _module_level_bindings(tree: ast.Module) -> dict[str, ast.expr]:
    """Each module-level ``NAME = <expression>``, by name — the last binding wins, as it would
    when the file ran."""
    bindings: dict[str, ast.expr] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = statement.value
    return bindings


def _string_constants(node: ast.AST) -> Iterator[str]:
    """The strings in a literal list, tuple or set — and in a dict's VALUES only, since an
    ``extras_require`` key names an extra, never a distribution."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.Dict):
        for value in node.values:
            yield from _string_constants(value)
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for item in node.elts:
            yield from _string_constants(item)
