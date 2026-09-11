# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Enforces that mutation testing's package classification (``pyproject.toml``) is a COMPLETE,
default-deny account of every ``packages/*/`` directory -- the mutation-testing sibling of
``test_coverage_source_completeness.py``'s ``[tool.coverage.run] source`` /
``[tool.coverage.narrativetrace_exempt]`` pattern.

Before 2026-09-10, the mutation-tested package set existed only as ``scripts/mutation_gate.py``'s
own hand-maintained ``_PACKAGES`` dict, and the ``poe mutate``/``poe mutate-glossary`` task pair
in ``pyproject.toml`` spelled the same two names out again. Nothing checked either copy against
the workspace: a new ``packages/*/`` directory could ship unmutated forever and nothing would say
so.

The fix is not a bigger list; it is that every ``packages/*/`` directory must now be in exactly
one of two places: mutation-tested (its directory name a key under
``[tool.narrativetrace.mutation.tested]``, mapped to its equivalent-mutant ledger path), or
exempt with a one-line, verified reason (a key under ``[tool.narrativetrace.mutation.exempt]``).
A directory that is neither -- or, just as much a bug, somehow both -- fails this test by name.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    """Walks up to the directory holding both the root ``pyproject.toml`` and ``packages/``
    instead of counting parents: under ``mutmut`` this suite re-runs from a copied tree one
    level deeper (``packages/narrativetrace/mutants/tests/``), where a fixed ``parents[3]``
    lands on ``packages/`` and opens a file that does not exist (nightly 2026-09-11)."""
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


def _package_directory_names() -> list[str]:
    return sorted(p.name for p in _PACKAGES_DIR.iterdir() if p.is_dir())


class TestMutationAccountingIsComplete:
    """Runs per commit (a plain test, collected by every ordinary ``poe test``/``poe coverage``/
    ``poe check`` run) -- this is a CHEAP config-consistency check only: it reads ``pyproject.toml``
    and lists a directory, never invoking ``mutmut``, so it carries none of the minutes-long cost
    of ``poe mutate``/``poe mutate-gate`` (scheduled/on-demand only, same cadence as fuzzing).
    It must catch a newly-unaccounted package the day it is introduced, not on some later audit.
    """

    def test_every_package_is_tested_or_exempted_never_neither_never_both(self) -> None:
        pyproject = _load_pyproject()
        tested = set(_lookup(pyproject, "tool", "narrativetrace", "mutation", "tested"))
        exempt = set(_lookup(pyproject, "tool", "narrativetrace", "mutation", "exempt"))
        assert exempt, "the exemption table itself vanished from pyproject.toml"

        names = _package_directory_names()
        unclassified = [name for name in names if name not in tested and name not in exempt]
        double_classified = [name for name in names if name in tested and name in exempt]

        assert unclassified == [], (
            "packages/*/ director(ies) neither mutation-tested "
            "([tool.narrativetrace.mutation.tested]) nor exempted with a reason "
            f"([tool.narrativetrace.mutation.exempt]): {unclassified} -- add each to one or the "
            "other in pyproject.toml"
        )
        assert double_classified == [], (
            "packages/*/ director(ies) classified as BOTH mutation-tested and exempt: "
            f"{double_classified} -- remove each from one of the two tables in pyproject.toml"
        )

    def test_every_tested_and_exempt_entry_still_names_a_real_package_directory(self) -> None:
        """The inverse direction: a renamed or removed package must not leave a stale entry
        behind claiming to test, or to have a reason to exempt, something that no longer exists --
        which would silently mask the next real gap sitting beside it."""
        pyproject = _load_pyproject()
        tested = set(_lookup(pyproject, "tool", "narrativetrace", "mutation", "tested"))
        exempt = set(_lookup(pyproject, "tool", "narrativetrace", "mutation", "exempt"))
        real_names = set(_package_directory_names())

        assert tested - real_names == set(), (
            "[tool.narrativetrace.mutation.tested] names no packages/*/ directory declares: "
            f"{tested - real_names}"
        )
        assert exempt - real_names == set(), (
            "[tool.narrativetrace.mutation.exempt] names no packages/*/ directory declares: "
            f"{exempt - real_names}"
        )

    def test_every_tested_packages_ledger_path_exists(self) -> None:
        """`[tool.narrativetrace.mutation.tested]` is a name -> ledger-path map, not a bare set --
        the one piece of per-package data mutation accounting needs beyond coverage's. A path that
        does not resolve on disk is the same class of drift as a stale name: `scripts/
        mutation_gate.py` would fail confusingly deep inside a real `poe mutate-gate` run instead
        of here, cheaply, per commit."""
        pyproject = _load_pyproject()
        tested: dict[str, str] = _lookup(pyproject, "tool", "narrativetrace", "mutation", "tested")

        missing = [name for name, ledger in tested.items() if not (_REPO_ROOT / ledger).is_file()]

        assert missing == [], (
            f"[tool.narrativetrace.mutation.tested] ledger path(s) missing on disk: {missing}"
        )
