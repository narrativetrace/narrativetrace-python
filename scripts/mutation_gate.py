# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Mutation kill-rate floor (`poe mutate-gate`, `poe mutate-glossary-gate`).

By design, every mutated package must kill at least 80% of its mutants, computed as
``killed / (total - ledgered equivalents)``. This script reads the mutmut results `poe mutate`/
`poe mutate-glossary` (a sequence step run just before this one) already produced under
``packages/<package>/mutants``, cross-references that package's own equivalent-mutant ledger,
and fails the build below the floor. One package per invocation (`argv[1]`, default
``narrativetrace``) — mutmut has no multi-root mode, so each mutated package's run and ledger
are independent; ``[tool.narrativetrace.mutation.tested]`` in the root ``pyproject.toml`` is
where a future third mutated package registers (see ``_load_packages`` below).

A ledgered mutant only shrinks the denominator while mutmut still reports it as "survived". One
that a later test happens to kill is simply counted as killed like any other mutant, not
double-credited — the ledger can never inflate the score for a mutant that stopped being
equivalent.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

FLOOR = 0.80
REPO_ROOT = Path(__file__).resolve().parent.parent
_RESULT_LINE = re.compile(r"^\s*(\S+):\s*(\S+)\s*$")


@dataclass(frozen=True)
class MutatedPackage:
    """Where one mutmut-mutated package's working copy and equivalent-mutant ledger live."""

    package_dir: Path
    ledger_path: Path


def _load_packages() -> dict[str, MutatedPackage]:
    """Reads the mutation-tested package set from its single source of truth --
    `[tool.narrativetrace.mutation.tested]` in the root `pyproject.toml` -- instead of keeping a
    second, hand-synced copy in this module. Default-deny accounting for the whole set (every
    `packages/*/` directory in exactly one of `tested` there or
    `[tool.narrativetrace.mutation.exempt]`, never neither, never both) is
    `packages/narrativetrace/tests/test_mutation_accounting.py`'s job, not this script's — this
    function only reads what that table says.
    """
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    tested: dict[str, str] = pyproject["tool"]["narrativetrace"]["mutation"]["tested"]
    return {
        name: MutatedPackage(REPO_ROOT / "packages" / name, REPO_ROOT / ledger)
        for name, ledger in tested.items()
    }


_PACKAGES: dict[str, MutatedPackage] = _load_packages()


def parse_ledger(text: str) -> dict[str, str]:
    """Parse `mutation/equivalents.txt`'s `<mutant id>\\t<reason>` lines into a dict.

    Blank lines and lines starting with ``#`` (after stripping leading whitespace) are comments.
    """
    entries: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        mutant_id, _, reason = stripped.partition("\t")
        entries[mutant_id.strip()] = reason.strip()
    return entries


def parse_survived_ids(results_text: str) -> set[str]:
    """Extract the mutant ids `mutmut results` reports as ``survived``."""
    return {
        match.group(1)
        for line in results_text.splitlines()
        if (match := _RESULT_LINE.match(line)) and match.group(2) == "survived"
    }


def compute_score(
    total: int, killed: int, ledger_ids: set[str], survived_ids: set[str]
) -> tuple[float, int]:
    """Return (kill rate, ledgered-and-still-surviving count) for the floor check.

    Raises ValueError if excluding the ledger would leave no mutants to score — a
    misconfiguration (an over-broad ledger), never a legitimate outcome.
    """
    excluded = len(ledger_ids & survived_ids)
    denominator = total - excluded
    if denominator <= 0:
        raise ValueError("no mutants left to score after excluding the ledger")
    return killed / denominator, excluded


def _run_mutmut(args: list[str], package_dir: Path) -> str:
    result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        ["mutmut", *args], cwd=package_dir, capture_output=True, text=True, check=True
    )
    return result.stdout


def _report(stats: dict[str, int], score: float, excluded: int, stale: list[str]) -> None:
    scored = stats["total"] - excluded
    print(
        f"mutation kill rate: {score:.1%} ({stats['killed']}/{scored} scored, "
        f"{excluded} ledgered equivalent(s) excluded, {stats['total']} mutants total)"
    )
    if stale:
        noun = "entry is" if len(stale) == 1 else "entries are"
        print(
            f"note: {len(stale)} ledger {noun} no longer surviving (not excluded): "
            f"{', '.join(stale)}"
        )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    package = args[0] if args else "narrativetrace"
    target = _PACKAGES.get(package)
    if target is None:
        print(f"unknown package {package!r}; expected one of {sorted(_PACKAGES)}", file=sys.stderr)
        return 2

    ledger = parse_ledger(target.ledger_path.read_text(encoding="utf-8"))
    survived_ids = parse_survived_ids(_run_mutmut(["results"], target.package_dir))
    _run_mutmut(["export-cicd-stats"], target.package_dir)
    stats_path = target.package_dir / "mutants" / "mutmut-cicd-stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8"))

    score, excluded = compute_score(stats["total"], stats["killed"], set(ledger), survived_ids)
    stale = sorted(set(ledger) - survived_ids)
    _report(stats, score, excluded, stale)

    if score < FLOOR:
        print(f"FAIL: kill rate {score:.1%} is below the {FLOOR:.0%} floor.")
        return 1
    print(f"PASS: kill rate {score:.1%} meets the {FLOOR:.0%} floor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
