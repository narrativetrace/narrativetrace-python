# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Minimal version-specifier matcher covering exactly the shapes this repository's own
``pyproject.toml`` files use (``>=3.12``, ``pytest>=8``): the doctor never needs to parse an
arbitrary PEP 440 specifier, only the comma-separated ``>=``/``>``/``<=``/``<``/``==``/``!=``
clauses ``requires-python`` and a ``Requires-Dist`` entry actually emit here. A real ``packaging``
dependency would cover forms this codebase never writes, at the cost of the core distribution's
"dependency-free" invariant. Mirrors the TypeScript runtime's ``semver-lite.ts`` (same scope note,
same "only what this repo emits" discipline) in Python's own version grammar.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_CLAUSE_RE = re.compile(r"(>=|<=|==|!=|>|<)\s*([0-9][0-9.]*)")


def parse_version(raw: str) -> tuple[int, int, int] | None:
    """Parses ``"3.12.4"``, ``"3.12"``, or ``"3"`` — missing parts default to zero. ``None`` when
    ``raw`` carries no leading digits at all."""
    match = _VERSION_RE.match(raw.strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return (int(major), int(minor or 0), int(patch or 0))


def _compare(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    """Three-way compare, standard sign convention: negative if ``left`` < ``right``."""
    for a, b in zip(left, right, strict=True):
        if a != b:
            return a - b
    return 0


_OPERATORS: dict[str, Callable[[int], bool]] = {
    ">=": lambda cmp: cmp >= 0,
    ">": lambda cmp: cmp > 0,
    "<=": lambda cmp: cmp <= 0,
    "<": lambda cmp: cmp < 0,
    "==": lambda cmp: cmp == 0,
    "!=": lambda cmp: cmp != 0,
}


def _satisfies_clause(version: tuple[int, int, int], clause: str) -> bool:
    match = _CLAUSE_RE.match(clause.strip())
    if not match:
        return False
    operator, raw_bound = match.groups()
    # `_CLAUSE_RE` already requires `raw_bound` to start with a digit, so `parse_version` always
    # resolves it -- unlike `parse_version`'s own public contract, there is no unparseable case
    # to guard here.
    bound = parse_version(raw_bound)
    assert bound is not None  # postcondition (Contract-Augmented TDD), not reachable in practice
    return _OPERATORS[operator](_compare(version, bound))


def satisfies(version_raw: str, specifier: str) -> bool:
    """Whether ``version_raw`` satisfies every comma-separated clause of ``specifier`` (AND
    semantics — the only combinator ``requires-python``/``Requires-Dist`` use here). Unparseable
    input on either side is a mismatch, never a throw — a doctor check reports a finding, it does
    not crash the run."""
    version = parse_version(version_raw)
    if version is None:
        return False
    clauses = [clause.strip() for clause in specifier.split(",") if clause.strip()]
    if not clauses:
        return False
    return all(_satisfies_clause(version, clause) for clause in clauses)


def dependency_specifier(requires: tuple[str, ...], distribution_name: str) -> str | None:
    """The version specifier ``distribution_name`` is pinned to inside ``requires`` (a package's
    ``Requires-Dist`` list), e.g. ``dependency_specifier(("pytest>=8",), "pytest") == ">=8"``.
    ``None`` when ``distribution_name`` is not a dependency at all."""
    prefix = re.compile(rf"^{re.escape(distribution_name)}\s*([<>=!].*)?$")
    for entry in requires:
        # A `Requires-Dist` entry may carry an environment marker after `;` (e.g. extras) — never
        # emitted by this repo's own packages today, but stripped defensively so a marker's own
        # text is never mistaken for part of the version specifier.
        name_and_specifier = entry.split(";", 1)[0].strip()
        match = prefix.match(name_and_specifier)
        if match:
            return (match.group(1) or "").strip() or None
    return None
