# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Enforces that ``[tool.coverage.run] source`` (``pyproject.toml``) is a COMPLETE list, not a
hand-maintained one that silently drifts.

Before 2026-09-10, nothing checked this: it was a plain array, edited by memory whenever a new
package was added. ``narrativetrace_pytest`` -- 319 real lines behind a shipped ``pytest11`` entry
point -- was silently absent, and so silently ungated: its tests ran and counted toward pass/fail,
but its own source was never instrumented, let alone measured against ``fail_under``, because
``coverage.py``'s ``source`` restricts instrumentation to exactly the names listed.

The fix is not a bigger list; it is that every ``packages/*/`` directory must now be in exactly
one of two places: measured (its import name in ``source``), or named with a reason in
``[tool.coverage.narrativetrace_exempt]``. A package that is neither fails this test by name --
an absence someone chose and documented is fine; an absence nobody can explain is what this
closes.

``[tool.coverage.narrativetrace_extra_source]`` (2026-09-13) accounts for the inverse case: a
``source`` entry that is a bare path rather than a packages/*/ import name, for code that is
still house-standard production code (test-driven, coverage-gated) but does not live under a
``src/<name>`` layout -- e.g. ``packages/narrativetrace-skills/evals``, the Tier B eval runner.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    """Walks up to the directory holding both the root ``pyproject.toml`` and ``packages/``
    instead of counting parents — same reason as ``test_mutation_accounting._find_repo_root``:
    under ``mutmut`` the suite re-runs from a copied tree one level deeper, where a fixed
    ``parents[3]`` opens a file that does not exist."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "packages").is_dir():
            return candidate
    raise RuntimeError(f"no workspace root (pyproject.toml + packages/) above {__file__}")


_REPO_ROOT = _find_repo_root()
_PACKAGES_DIR = _REPO_ROOT / "packages"


def _load_pyproject() -> dict[str, object]:
    with (_REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _lookup(pyproject: dict[str, object], *keys: str) -> Any:
    """Walks a nested TOML-parsed mapping by key path. Deliberately ``Any``-typed at the
    boundary -- every call site immediately narrows with ``set(...)``/``dict(...)`` -- rather
    than making every caller carry ``isinstance`` narrowing for structure a missing key already
    raises ``KeyError`` on, which reads as this test's own failure (a malformed
    ``pyproject.toml`` is exactly this test's business)."""
    node: Any = pyproject
    for key in keys:
        node = node[key]
    return node


def _package_directories() -> list[Path]:
    return sorted(p for p in _PACKAGES_DIR.iterdir() if p.is_dir())


def _import_name(package_dir: Path) -> str | None:
    """The importable package name a ``packages/<dir>/src/*`` layout declares, or ``None`` when
    the directory carries no single ``src/<name>/__init__.py`` -- nothing importable to measure,
    so nothing this test asks `source`/the exemption table to account for."""
    src = package_dir / "src"
    if not src.is_dir():
        return None
    candidates = [
        child.name
        for child in src.iterdir()
        if child.is_dir() and (child / "__init__.py").is_file()
    ]
    return candidates[0] if len(candidates) == 1 else None


class TestCoverageSourceListIsComplete:
    """Runs per commit (a plain test, collected by every ordinary ``poe test``/``poe coverage``
    run) -- this must catch the gap the day it is introduced, not on some later audit."""

    def test_every_package_is_measured_or_explicitly_exempted(self) -> None:
        pyproject = _load_pyproject()
        source = set(_lookup(pyproject, "tool", "coverage", "run", "source"))
        exempt = _lookup(pyproject, "tool", "coverage", "narrativetrace_exempt")
        assert exempt, "the exemption table itself vanished from pyproject.toml"

        unaccounted = [
            name
            for package_dir in _package_directories()
            if (name := _import_name(package_dir)) is not None
            and name not in source
            and name not in exempt
        ]

        assert unaccounted == [], (
            "packages/*/ import name(s) neither measured in [tool.coverage.run] source nor "
            f"exempted with a reason in [tool.coverage.narrativetrace_exempt]: {unaccounted} -- "
            "add each to one or the other in pyproject.toml"
        )

    def test_every_source_entry_and_exemption_still_names_a_real_package(self) -> None:
        """The inverse direction: a renamed or removed package must not leave a stale entry
        behind claiming to measure, or to have a reason to exempt, something that no longer
        exists -- which would silently mask the next real gap sitting beside it.

        ``[tool.coverage.narrativetrace_extra_source]`` is the one documented exception: a
        ``source`` entry that is a bare path, not a packages/*/ import name (2026-09-13, the
        Tier B eval runner under ``packages/narrativetrace-skills/evals/`` -- not a
        ``src/<name>`` layout, so it has no import name to appear in ``real_names``). Entries
        there are subtracted before this check, so a *documented* extra path is fine; an
        undocumented one still fails it.
        """
        pyproject = _load_pyproject()
        source = set(_lookup(pyproject, "tool", "coverage", "run", "source"))
        exempt = set(_lookup(pyproject, "tool", "coverage", "narrativetrace_exempt"))
        extra_source = set(_lookup(pyproject, "tool", "coverage", "narrativetrace_extra_source"))
        real_names = {
            name
            for package_dir in _package_directories()
            if (name := _import_name(package_dir)) is not None
        }

        assert source - real_names - extra_source == set(), (
            f"[tool.coverage.run] source names no packages/*/ directory declares and no "
            f"[tool.coverage.narrativetrace_extra_source] entry accounts for: "
            f"{source - real_names - extra_source}"
        )
        assert exempt - real_names == set(), (
            f"[tool.coverage.narrativetrace_exempt] names no packages/*/ directory declares: "
            f"{exempt - real_names}"
        )

    def test_every_extra_source_entry_exists_on_disk(self) -> None:
        """The mutation-accounting sibling check (``test_every_tested_packages_ledger_path_exists``)
        for this table: a documented extra ``source`` path that doesn't resolve on disk is the
        same class of drift as a stale name, just quieter -- coverage.py silently measures
        nothing for a missing directory instead of erroring."""
        pyproject = _load_pyproject()
        extra_source = _lookup(pyproject, "tool", "coverage", "narrativetrace_extra_source")

        missing = [path for path in extra_source if not (_REPO_ROOT / path).is_dir()]

        assert missing == [], (
            f"[tool.coverage.narrativetrace_extra_source] path(s) missing on disk: {missing}"
        )
