# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Builds a :class:`~narrativetrace.doctor.types.DoctorSnapshot` from the real filesystem and the
running interpreter's installed-distribution metadata. The one impure module in the doctor package
— mirrors the TypeScript runtime's ``doctor/environment.ts`` (bounded breadth-first walk, bucketed
into source/output/approved-dir files) in Python's own idiom (``importlib.metadata`` instead of
``require.resolve``, ``tomllib`` instead of parsing ``package.json``).
"""

from __future__ import annotations

import os
import sys
import tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path

from narrativetrace.config import ConfigResolver
from narrativetrace.doctor.types import DoctorSnapshot, Env, PackageInfo

_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".tox",
        "htmlcov",
        "mutants",
        ".mutmut-cache",
        "node_modules",
        ".hypothesis",
    }
)

_SOURCE_EXTENSIONS = (".py", ".toml", ".ini", ".cfg")

_MAX_FILES = 20_000

_KNOWN_DISTRIBUTIONS = (
    "narrativetrace",
    "narrativetrace-asgi",
    "narrativetrace-clarity",
    "narrativetrace-diagrams",
    "narrativetrace-glossary",
    "narrativetrace-otel",
    "narrativetrace-pytest",
    "narrativetrace-structlog",
    "pytest",
    "structlog",
)


def _resolve_package_info(name: str) -> PackageInfo | None:
    try:
        dist = importlib_metadata.distribution(name)
    except importlib_metadata.PackageNotFoundError:
        return None
    requires = tuple(dist.requires or ())
    return PackageInfo(
        name=name,
        version=dist.version,
        requires_python=dist.metadata.get("Requires-Python"),
        requires=requires,
    )


def _resolve_installed_packages() -> dict[str, PackageInfo]:
    installed: dict[str, PackageInfo] = {}
    for name in _KNOWN_DISTRIBUTIONS:
        info = _resolve_package_info(name)
        if info is not None:
            installed[name] = info
    return installed


def _resolve_pytest11_entry_points() -> dict[str, str]:
    entry_points = importlib_metadata.entry_points(group="pytest11")
    return {entry_point.name: entry_point.value for entry_point in entry_points}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _load_pyproject(path: Path) -> dict[str, object] | None:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _load_root_pyproject(cwd: Path) -> dict[str, object] | None:
    """The nearest readable ``pyproject.toml``, walking up from ``cwd`` — the same upward-walk
    convention :class:`~narrativetrace.config.ConfigResolver` already uses, so ``narrativetrace
    doctor`` works from a project subdirectory the same way the runtime's own configuration
    discovery already does, not only from a project's exact root."""
    for directory in (cwd, *cwd.parents):
        table = _load_pyproject(directory / "pyproject.toml")
        if table is not None:
            return table
    return None


def _classify(relative: str, output_dir_name: str, approved_dir_name: str) -> str:
    top = relative.split(os.sep, 1)[0]
    if top == output_dir_name:
        return "output"
    if top == approved_dir_name:
        return "approved"
    return "source" if relative.endswith(_SOURCE_EXTENSIONS) else "skip"


class _Walker:
    """Bounded breadth-first walk, bucketing files into source/output/approved-dir — excluding
    virtualenvs, caches, and build noise. Bounded by :data:`_MAX_FILES` so a doctor run in a huge
    repo degrades to a partial scan rather than hanging."""

    def __init__(self, root: Path, output_dir_name: str, approved_dir_name: str) -> None:
        self._root = root
        self._output_dir_name = output_dir_name
        self._approved_dir_name = approved_dir_name
        self.source_files: dict[str, str] = {}
        self.output_files: dict[str, str] = {}
        self.approved_dir_files: dict[str, str] = {}
        self._visited = 0

    def _bucket_for(self, kind: str) -> dict[str, str]:
        return {
            "output": self.output_files,
            "approved": self.approved_dir_files,
            "source": self.source_files,
        }[kind]

    def _visit_file(self, path: Path) -> None:
        self._visited += 1
        relative = str(path.relative_to(self._root))
        kind = _classify(relative, self._output_dir_name, self._approved_dir_name)
        if kind == "skip":
            return
        self._bucket_for(kind)[relative] = _read_text(path)

    def walk(self) -> None:
        queue = [self._root]
        while queue and self._visited < _MAX_FILES:
            directory = queue.pop(0)
            try:
                entries = sorted(directory.iterdir())
            except OSError:
                continue
            for entry in entries:
                if self._visited >= _MAX_FILES:
                    break
                name = entry.name
                if name.startswith(".") and name != ".env":
                    continue
                if entry.is_dir():
                    if name not in _EXCLUDED_DIRS:
                        queue.append(entry)
                    continue
                self._visit_file(entry)


def build_snapshot(cwd: str, env: Env) -> DoctorSnapshot:
    """Builds a :class:`~narrativetrace.doctor.types.DoctorSnapshot` from the real filesystem
    rooted at ``cwd``."""
    root = Path(cwd)
    resolver = ConfigResolver(start_dir=root)
    config = resolver.file_values
    output_dir_name = str(config.get("output_dir") or "narrative-traces")
    approved_dir_name = str(config.get("approved_dir") or "test-narratives")
    walker = _Walker(root, output_dir_name, approved_dir_name)
    walker.walk()
    return DoctorSnapshot(
        cwd=str(root),
        python_version=".".join(str(part) for part in sys.version_info[:3]),
        env=env,
        root_pyproject=_load_root_pyproject(root),
        narrativetrace_config=config,
        source_files=walker.source_files,
        output_files=walker.output_files,
        approved_dir_files=walker.approved_dir_files,
        installed_packages=_resolve_installed_packages(),
        pytest11_entry_points=_resolve_pytest11_entry_points(),
    )
