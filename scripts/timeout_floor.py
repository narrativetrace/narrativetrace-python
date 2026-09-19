# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Per-commit gate: every `@pytest.mark.timeout(<n>)` marker meets the documented hang-guard
floor (`poe timeout-floor`, wired into `poe check` next to `deep-fixture-budget`).

Release retrospective rule 3 refinement (Pro ledger #129): a timeout on a test whose assertion is
not about time is a HANG GUARD, not a tolerance. It must be seconds-scale by design -- a fixed,
documented floor -- and never derived from a timing sample. Deriving a budget as "N times a
measured/contended sample" still makes wall-clock a test input: there is always a worse sample,
and `TestParseCacheIsBounded` (`packages/narrativetrace/tests/test_template.py`) went red under
ordinary scheduler starvation at a sample-derived 0.8s budget. The fix is not a bigger sample,
it's no sample: every hang guard in this repository carries the same fixed floor.

A genuine timing assertion (the test *is* about latency/throughput) must not use pytest-timeout as
the assertion at all -- it belongs in the benchmark/scheduled tier (`test_bench_*.py`, `poe bench`
/ `poe bench-gate`) or asserts on measured work with a generous bound. So this gate does not
special-case "timing tests": every `@pytest.mark.timeout(...)` marker in the suite is a hang guard
by definition, and every one of them must meet the floor.

Detects, inside every `test_*` function under `packages/*/tests/**/*.py` and
`examples/**/test_*.py` (mirrors `[tool.pytest.ini_options].testpaths`), a
`@pytest.mark.timeout(<literal number>)` decorator whose value is below `TIMEOUT_FLOOR_SECONDS`.
A match is a violation unless the test id is named, with a reason, in
`scripts/timeout-floor-allowlist.json`; a stale entry (naming a test id that no longer carries a
sub-floor marker) fails the gate too, mirroring `deep_fixture_budget`'s allowlist idiom.
"""

from __future__ import annotations

import ast
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent)
)  # scripts/contract_lint.py's cross-import convention

from scripts.deep_fixture_budget import test_files

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH: Final = REPO_ROOT / "scripts" / "timeout-floor-allowlist.json"

#: The documented hang-guard floor (seconds). Fixed by convention -- never derived from a timing
#: sample. See the module docstring and `documentation/security-testing.md`'s test-guide section.
TIMEOUT_FLOOR_SECONDS: Final = 10.0


def _timeout_value(decorator: ast.expr) -> float | None:
    """The numeric argument of a `@pytest.mark.timeout(<n>)` decorator, or ``None`` if
    `decorator` is not that call (a different mark, a bare name, a non-literal argument)."""
    if not isinstance(decorator, ast.Call):
        return None
    target = decorator.func
    if not (
        isinstance(target, ast.Attribute)
        and target.attr == "timeout"
        and isinstance(target.value, ast.Attribute)
        and target.value.attr == "mark"
        and isinstance(target.value.value, ast.Name)
        and target.value.value.id == "pytest"
    ):
        return None
    if len(decorator.args) != 1:
        return None
    (arg,) = decorator.args
    if (
        isinstance(arg, ast.Constant)
        and isinstance(arg.value, (int, float))
        and not isinstance(arg.value, bool)
    ):
        return float(arg.value)
    return None


def _iter_test_functions(
    module: ast.Module,
) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every `test_*` function, module-level or one class deep (`TestFoo.test_bar`) -- this
    codebase never nests test classes further."""
    found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []

    def walk(body: list[ast.stmt], prefix: str) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                walk(stmt.body, f"{prefix}{stmt.name}.")
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith(
                "test_"
            ):
                found.append((f"{prefix}{stmt.name}", stmt))

    walk(module.body, "")
    return found


@dataclass(frozen=True)
class TimeoutMarkerHit:
    """One `test_*` function carrying a `@pytest.mark.timeout(<n>)` marker below the documented
    floor. `test_id` is `<repo-relative POSIX path>::<qualified name>`."""

    test_id: str
    line: int
    value: float


@dataclass(frozen=True)
class BudgetResult:
    """`violations`: sub-floor markers outside the allowlist -- a red gate. `stale_allowlist_
    entries`: allowlist entries naming a test id that no longer carries a sub-floor marker."""

    violations: tuple[TimeoutMarkerHit, ...]
    stale_allowlist_entries: tuple[str, ...]


def find_sub_floor_markers(repo_root: Path) -> list[TimeoutMarkerHit]:
    """Every `test_*` function across the suite carrying a `@pytest.mark.timeout(<n>)` marker
    with `n < TIMEOUT_FLOOR_SECONDS`, sorted by test id."""
    hits: list[TimeoutMarkerHit] = []
    for path in test_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for qualname, func in _iter_test_functions(tree):
            for decorator in func.decorator_list:
                value = _timeout_value(decorator)
                if value is not None and value < TIMEOUT_FLOOR_SECONDS:
                    hits.append(
                        TimeoutMarkerHit(
                            test_id=f"{relative}::{qualname}", line=func.lineno, value=value
                        )
                    )
    return sorted(hits, key=lambda hit: hit.test_id)


def check(repo_root: Path, allowlist: Mapping[str, str]) -> BudgetResult:
    hits = find_sub_floor_markers(repo_root)
    hit_ids = {hit.test_id for hit in hits}
    violations = tuple(hit for hit in hits if hit.test_id not in allowlist)
    stale = tuple(sorted(test_id for test_id in allowlist if test_id not in hit_ids))
    return BudgetResult(violations=violations, stale_allowlist_entries=stale)


def _load_allowlist(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a JSON object mapping test id -> reason")
    return {str(key): str(value) for key, value in raw.items()}


def main() -> int:
    allowlist = _load_allowlist(ALLOWLIST_PATH)
    result = check(REPO_ROOT, allowlist)
    allowlist_rel = ALLOWLIST_PATH.relative_to(REPO_ROOT).as_posix()

    if result.violations:
        print(
            f"timeout-floor: {len(result.violations)} @pytest.mark.timeout(...) marker(s) below "
            f"the {TIMEOUT_FLOOR_SECONDS}s documented floor (release retrospective rule 3 "
            "refinement, Pro ledger #129 -- a hang guard is a fixed floor, never a timing "
            "sample):"
        )
        for hit in result.violations:
            path, _, qualname = hit.test_id.partition("::")
            print(f"  {path}:{hit.line}: {qualname} (timeout={hit.value})")
        print(f"  (add a reasoned entry to {allowlist_rel} only for a genuine exception)")
        return 1

    if result.stale_allowlist_entries:
        print(
            f"timeout-floor: {len(result.stale_allowlist_entries)} stale allowlist entry(ies) "
            f"-- no longer a sub-floor marker, remove from {allowlist_rel}:"
        )
        for test_id in result.stale_allowlist_entries:
            print(f"  {test_id}")
        return 1

    print(
        f"timeout-floor: every @pytest.mark.timeout(...) marker meets the {TIMEOUT_FLOOR_SECONDS}s "
        f"floor ({len(allowlist)} reasoned exception(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
