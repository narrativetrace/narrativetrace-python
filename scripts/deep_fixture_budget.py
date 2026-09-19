# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Per-commit gate: every deep-fixture (10,000+/50,000+ node chain/tree) test declares its own
wall-clock budget (`poe deep-fixture-budget`, wired into `poe check` next to `comment-hygiene`).

Release retrospective rule 3: wall-clock/GC/scheduler are never test inputs -- a test whose
legitimate cost scales with a large fixture must never rely on an implicit default (pytest has
none of its own; the implicit default this guards against is "whatever this machine happens to be
fast enough for today"). `test(examples): artifact round-trip compares content, not live
durations` gave the first 19 such tests an explicit `@pytest.mark.timeout(<n>)` (pytest-timeout);
this script keeps the class from regrowing silently.

Detects, inside every `test_*` function under `packages/*/tests/**/*.py` and
`examples/**/test_*.py` (mirrors `[tool.pytest.ini_options].testpaths`), either shape a deep
fixture is built in:

- a `for ... in range(N):` loop with N in (10_000, 50_000) -- the direct, hand-rolled chain build
  most of these tests use;
- a call to a known chain/nested-container builder (`chain`, `deep_chain`, `nest_lists`, with or
  without a leading underscore or a `self.`/module prefix) passed a literal depth of 10_000 or
  50_000.

Only ever reasons about the AST -- never string/comment content -- and never descends into a
nested `def`/`class`/`lambda` inside the test body (a large fixture built by a *helper* the test
merely calls is attributed to the call site, not chased into the helper's own body). A match with
no `@pytest.mark.timeout(...)` decorator is a violation unless the test id is named, with a
reason, in `scripts/deep-fixture-budget-allowlist.json`; a stale entry (naming a test id no
longer detected as a large-fixture test at all) fails the gate too, mirroring `comment_hygiene`'s
per-file allowlist idiom.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH: Final = REPO_ROOT / "scripts" / "deep-fixture-budget-allowlist.json"
TEST_ROOTS: Final = ("packages", "examples")
_SKIP_DIR_NAMES: Final = frozenset(
    {"mutants", "__pycache__", "build", "dist", "node_modules", "venv", "{arch}", "_darcs", "CVS"}
)

_LARGE_SIZES: Final = frozenset({10_000, 50_000})
_BUILDER_NAME_RE: Final = re.compile(r"^_?(deep_)?chain$|^_?nest_lists$", re.IGNORECASE)


def test_files(repo_root: Path) -> list[Path]:
    """Every `test_*.py` file under `<repo_root>/{packages,examples}/**`, sorted; skips the same
    directory shapes `[tool.pytest.ini_options].norecursedirs` does (mutants, caches, hidden
    dirs, build output) since this walks the filesystem itself rather than asking pytest."""
    files: list[Path] = []
    for root_name in TEST_ROOTS:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("test_*.py"):
            if path.suffix != ".py":
                continue
            if any(
                part in _SKIP_DIR_NAMES or part.startswith(".")
                for part in path.relative_to(root).parts[:-1]
            ):
                continue
            files.append(path)
    return sorted(files)


def _int_value(node: ast.expr) -> int | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


def _call_name(node: ast.Call) -> str | None:
    """The called function's own simple name: `range` for `range(...)`, `_chain` for both
    `_chain(...)` and `self._chain(...)`."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _LargeFixtureVisitor(ast.NodeVisitor):
    """Walks one function's body (never descending into a nested `def`/`class`/`lambda`) and
    sets `found` if a 10,000+/50,000+ chain/tree fixture is built directly in it."""

    def __init__(self) -> None:
        self.found = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # ast.NodeVisitor's own naming
        return None  # do not descend: a helper this test calls is judged at its own call site

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]
    visit_ClassDef = visit_FunctionDef  # type: ignore[assignment]
    visit_Lambda = visit_FunctionDef  # type: ignore[assignment]

    def visit_For(self, node: ast.For) -> None:
        iterable = node.iter
        if isinstance(iterable, ast.Call) and _call_name(iterable) == "range":
            if any(_int_value(arg) in _LARGE_SIZES for arg in iterable.args):
                self.found = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name is not None and _BUILDER_NAME_RE.match(name) is not None:
            if any(_int_value(arg) in _LARGE_SIZES for arg in node.args):
                self.found = True
        self.generic_visit(node)


def _builds_a_large_fixture(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    visitor = _LargeFixtureVisitor()
    for stmt in func.body:
        visitor.visit(stmt)
    return visitor.found


def _has_timeout_marker(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in func.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        target = decorator.func
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "timeout"
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == "mark"
            and isinstance(target.value.value, ast.Name)
            and target.value.value.id == "pytest"
        ):
            return True
    return False


def _iter_test_functions(
    module: ast.Module,
) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Yields `(qualified_name, node)` for every `test_*` function, module-level or one class
    deep (`TestFoo.test_bar`) -- this codebase never nests test classes further."""

    def walk(
        body: list[ast.stmt], prefix: str
    ) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                yield from walk(stmt.body, f"{prefix}{stmt.name}.")
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith(
                "test_"
            ):
                yield f"{prefix}{stmt.name}", stmt

    yield from walk(module.body, "")


@dataclass(frozen=True)
class DeepFixtureHit:
    """One `test_*` function that builds a 10,000+/50,000+ node fixture. `test_id` is
    `<repo-relative POSIX path>::<qualified name>`; `has_marker` says whether it already carries
    `@pytest.mark.timeout(...)`."""

    test_id: str
    line: int
    has_marker: bool


@dataclass(frozen=True)
class BudgetResult:
    """`violations`: hits with no marker, outside the allowlist -- a red gate. `stale_allowlist_
    entries`: allowlist entries naming a test id no longer detected as a large-fixture test."""

    violations: tuple[DeepFixtureHit, ...]
    stale_allowlist_entries: tuple[str, ...]


def find_large_fixture_tests(repo_root: Path) -> list[DeepFixtureHit]:
    """Every `test_*` function across `test_files` that builds a 10,000+/50,000+ node fixture,
    sorted by test id."""
    hits: list[DeepFixtureHit] = []
    for path in test_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for qualname, func in _iter_test_functions(tree):
            if _builds_a_large_fixture(func):
                hits.append(
                    DeepFixtureHit(
                        test_id=f"{relative}::{qualname}",
                        line=func.lineno,
                        has_marker=_has_timeout_marker(func),
                    )
                )
    return sorted(hits, key=lambda hit: hit.test_id)


def check(repo_root: Path, allowlist: Mapping[str, str]) -> BudgetResult:
    hits = find_large_fixture_tests(repo_root)
    hit_ids = {hit.test_id for hit in hits}
    violations = tuple(hit for hit in hits if not hit.has_marker and hit.test_id not in allowlist)
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
            f"deep-fixture-budget: {len(result.violations)} large-fixture test(s) with no "
            "explicit @pytest.mark.timeout(...):"
        )
        for hit in result.violations:
            path, _, qualname = hit.test_id.partition("::")
            print(f"  {path}:{hit.line}: {qualname}")
        print(f"  (add a reasoned entry to {allowlist_rel} only for a genuine exception)")
        return 1

    if result.stale_allowlist_entries:
        print(
            f"deep-fixture-budget: {len(result.stale_allowlist_entries)} stale allowlist "
            f"entry(ies) -- no longer a large-fixture test, remove from {allowlist_rel}:"
        )
        for test_id in result.stale_allowlist_entries:
            print(f"  {test_id}")
        return 1

    print(
        "deep-fixture-budget: every deep chain/tree fixture test declares its own budget "
        f"({len(allowlist)} reasoned exception(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
