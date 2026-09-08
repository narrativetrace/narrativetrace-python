# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Layered configuration resolution with duplicate-source fail-fast.

``ConfigResolver`` / ``DuplicateConfigurationException``. Java resolves a key from a JVM
system property, then a single ``narrativetrace.properties`` on the classpath, then a default, and
treats two config files as a hard error rather than picking one silently.

The platform equivalents:

* **System property → environment variable.** ``NARRATIVETRACE_<KEY>`` (upper-cased, so ``level``
  reads ``NARRATIVETRACE_LEVEL`` and ``output_dir`` reads ``NARRATIVETRACE_OUTPUT_DIR``).
* **Classpath properties file → a TOML table**, either a standalone ``narrativetrace.toml`` or
  ``[tool.narrativetrace]`` inside ``pyproject.toml``. Parsed with stdlib :mod:`tomllib`, so the
  core distribution stays dependency-free.
* **Classpath scan → an upward directory walk** from the working directory. The nearest directory
  holding either file wins and the walk stops there.

Both files in the *same* directory raises :class:`DuplicateConfigurationError` — the
product-wide "two config files on one search path is a hard error, not silent precedence" rule.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

_ENV_PREFIX = "NARRATIVETRACE_"
_STANDALONE_FILE = "narrativetrace.toml"
_PYPROJECT_FILE = "pyproject.toml"


class DuplicateConfigurationError(Exception):
    """Raised when one directory holds more than one NarrativeTrace configuration source."""


def _pyproject_table(path: Path) -> dict[str, Any] | None:
    """Returns ``[tool.narrativetrace]`` from a ``pyproject.toml``, or ``None`` when absent."""
    document = _load_toml(path)
    table = document.get("tool", {}).get("narrativetrace") if document else None
    return table if isinstance(table, dict) else None


def _standalone_table(path: Path) -> dict[str, Any]:
    """Returns the whole ``narrativetrace.toml`` document, empty when malformed or unreadable."""
    return _load_toml(path) or {}


def _load_toml(path: Path) -> dict[str, Any] | None:
    """Parses a TOML file, degrading an unreadable or malformed file to ``None`` (as Java does)."""
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _canonical(value: Any) -> str:
    """Renders a TOML scalar the way a properties file would carry it (``true``, not ``True``)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class ConfigResolver:
    """Resolves configuration keys from environment, then a discovered TOML table, then defaults."""

    def __init__(self, start_dir: Path | None = None) -> None:
        self._table = _discover(Path(start_dir) if start_dir is not None else Path.cwd())

    @property
    def file_values(self) -> dict[str, Any]:
        """The discovered file table (empty when no configuration file was found)."""
        return dict(self._table)

    def resolve(self, key: str, default: str | None = None) -> str | None:
        """Returns the value for ``key``: environment, else file, else ``default``."""
        if not key:
            raise ValueError("key must not be empty")
        env_value = os.environ.get(_ENV_PREFIX + key.upper())
        if env_value is not None:
            return env_value
        if key in self._table:
            return _canonical(self._table[key])
        return default


def _discover(start_dir: Path) -> dict[str, Any]:
    """Walks up from ``start_dir`` and returns the nearest configuration table."""
    for directory in (start_dir, *start_dir.parents):
        table = _table_in(directory)
        if table is not None:
            return table
    return {}


def _table_in(directory: Path) -> dict[str, Any] | None:
    """Returns this directory's config table, failing fast when it holds two competing sources.

    A source counts as *declared* by its presence, not by whether it parses — a malformed
    ``narrativetrace.toml`` beside a ``[tool.narrativetrace]`` table is still the ambiguity the
    fail-fast exists to catch, and silently preferring the readable one would hide a broken file.
    """
    standalone = directory / _STANDALONE_FILE
    pyproject = directory / _PYPROJECT_FILE
    declares_standalone = standalone.is_file()
    from_pyproject = _pyproject_table(pyproject) if pyproject.is_file() else None
    if declares_standalone and from_pyproject is not None:
        raise DuplicateConfigurationError(
            f"Found competing NarrativeTrace configuration in {directory}: "
            f"{_STANDALONE_FILE} and {_PYPROJECT_FILE} [tool.narrativetrace]"
        )
    if declares_standalone:
        return _standalone_table(standalone)
    return from_pyproject
