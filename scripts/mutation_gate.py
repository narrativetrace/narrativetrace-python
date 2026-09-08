# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Mutation kill-rate floor (`poe mutate-gate`).

By design, the suite must kill at least 80% of mutants, computed as
``killed / (total - ledgered equivalents)``. This script reads the mutmut results `poe mutate`
(a `mutate-gate` sequence step run just before this one) already produced under
``packages/narrativetrace/mutants``, cross-references the equivalent-mutant ledger
(``mutation/equivalents.txt``), and fails the build below the floor.

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
from pathlib import Path

FLOOR = 0.80
REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "packages" / "narrativetrace"
LEDGER_PATH = REPO_ROOT / "mutation" / "equivalents.txt"
_RESULT_LINE = re.compile(r"^\s*(\S+):\s*(\S+)\s*$")


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


def _run_mutmut(args: list[str]) -> str:
    result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        ["mutmut", *args], cwd=PACKAGE_DIR, capture_output=True, text=True, check=True
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


def main() -> int:
    ledger = parse_ledger(LEDGER_PATH.read_text(encoding="utf-8"))
    survived_ids = parse_survived_ids(_run_mutmut(["results"]))
    _run_mutmut(["export-cicd-stats"])
    stats_path = PACKAGE_DIR / "mutants" / "mutmut-cicd-stats.json"
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
