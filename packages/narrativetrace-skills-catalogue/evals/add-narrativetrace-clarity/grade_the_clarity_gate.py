# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Grades the clarity skill's happy path: the gate runs clean on the project, and the project is
still the project.

THE CASE (``happy-path``)
-------------------------
Fixture ``clarity-unclear-name``: a small service that works, with names that say little
(``OrderService.proc(d, x)``, ``OrderService.calc(val, tmp)``, ``InvoiceFormatter.fmt(o)``). It
starts as a committed git repository, declares no NarrativeTrace dependency, and its tests call
``proc`` by keyword. The prompt asks for the gate and for the flagged names to be fixed so that no
HIGH issue remains and every class scores at least 0.6.

Expected trajectory: the agent adds ``narrativetrace-clarity`` as a development dependency, scans
``src``, reads the report, renames the three methods and their parameters (callers and tests with
them), and re-runs until the gate exits 0.

What fails, each with its own reason:

1. ``pyproject.toml`` does not declare ``narrativetrace-clarity``.
2. The gate, run here over ``src`` with the prompt's own thresholds, does not exit 0 -- or exits 0
   having scored a different number of classes than the project has (a scan that found nothing
   exits 0 too).
3. The project lost public methods: deleting code satisfies a naming gate trivially.
4. The project's tests fail, or fewer of them exist than at the start: a rename that moved the
   definition and not its callers, or a test deleted to make the suite pass.
5. ``--warn-only`` appears in any file the project owns: an advisory gate exits 0 whatever it found.

DELIBERATELY NOT A FAILURE: which names the agent chose, how it ran its own scans, or whether it
wrote the gate into CI. The gate is the judge of the names; the case measures that it ends clean.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

SOURCE: Final = "src"
MIN_SCORE: Final = "0.6"
MAX_HIGH_ISSUES: Final = "0"
PACKAGE: Final = "narrativetrace-clarity"
METHODS_AT_START: Final = 3
TESTS_AT_START: Final = 4
# `.agents` and `.claude` hold the skill pages the harness copies in, and the clarity skill's own
# page names the flag in a rule against it; `build` is where the agent's own scans write. Those
# three are the project root's alone: a `ci/build/` script is the project's.
_HARNESS_OWNED: Final = frozenset({".agents", ".claude", "build"})
_NEVER_THE_PROJECTS: Final = frozenset({".git", ".venv", "__pycache__", "node_modules"})
_NOT_NAME_CHARACTERS: Final = "<>=!~;[ ("


@dataclass(frozen=True, slots=True)
class Outcome:
    returncode: int
    stdout: str


Runner = Callable[[Sequence[str], Path], Outcome]


def _run(argv: Sequence[str], cwd: Path) -> Outcome:
    done = subprocess.run(  # nosec B603 - a fixed argv, in the trial's own scratch project
        list(argv), cwd=cwd, capture_output=True, text=True, check=False
    )
    return Outcome(done.returncode, done.stdout)


def _normalised(requirement: str) -> str:
    """The requirement's project name as PEP 503 spells it: lower case, runs of ``-``, ``_`` and
    ``.`` as one ``-``."""
    end = next(
        (i for i, c in enumerate(requirement) if c in _NOT_NAME_CHARACTERS), len(requirement)
    )
    return re.sub(r"[-_.]+", "-", requirement[:end].strip().lower())


def _declared_requirements(pyproject: dict[str, object]) -> list[str]:
    """Every requirement string the project file declares, wherever it sits."""
    project = pyproject.get("project", {})
    groups = pyproject.get("dependency-groups", {})
    found: list[object] = []
    if isinstance(project, dict):
        found.extend(project.get("dependencies", []))
        optional = project.get("optional-dependencies", {})
        for requirements in optional.values() if isinstance(optional, dict) else ():
            found.extend(requirements)
    for requirements in groups.values() if isinstance(groups, dict) else ():
        found.extend(requirements)
    return [r for r in found if isinstance(r, str)]


def _dependency_missing(project: Path) -> list[str]:
    try:
        pyproject = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["pyproject.toml is missing"]
    except tomllib.TOMLDecodeError:
        return ["pyproject.toml is not valid TOML"]
    if PACKAGE in {_normalised(r) for r in _declared_requirements(pyproject)}:
        return []
    return [f"pyproject.toml does not declare {PACKAGE}"]


def _public_shape(project: Path) -> tuple[int, int]:
    """The public classes and the public methods under ``src``."""
    classes = methods = 0
    for path in sorted((project / SOURCE).rglob("*.py")):
        relative = path.relative_to(project).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=relative)):
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                classes += 1
                methods += sum(
                    isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
                    and not m.name.startswith("_")
                    for m in node.body
                )
    return classes, methods


def _methods_lost(methods: int) -> list[str]:
    if methods >= METHODS_AT_START:
        return []
    return [f"the project has {methods} public methods; it started with {METHODS_AT_START}"]


def _scored(output_dir: Path) -> int:
    try:
        scenarios = json.loads((output_dir / "clarity-results.json").read_text(encoding="utf-8"))
        return sum(isinstance(s, dict) for s in scenarios["scenarios"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def _gate(project: Path, classes: int, run: Runner) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="nt-clarity-grade-") as output:
        argv = [
            "uv", "run", PACKAGE, SOURCE, "--output-dir", output,
            "--min-score", MIN_SCORE, "--max-high-issues", MAX_HIGH_ISSUES,
        ]  # fmt: skip
        outcome = run(argv, project)
        if outcome.returncode != 0:
            return [
                f"the gate exits {outcome.returncode} on `{SOURCE}` with "
                f"--min-score {MIN_SCORE} --max-high-issues {MAX_HIGH_ISSUES}"
            ]
        scored = _scored(Path(output))
    if scored == classes:
        return []
    return [f"the gate scored {scored} class(es); the project has {classes} public ones"]


def _tests(project: Path, run: Runner) -> list[str]:
    reasons: list[str] = []
    if run(["uv", "run", "pytest", "-q"], project).returncode != 0:
        reasons.append("the project's tests fail after the renames")
    collected = run(["uv", "run", "pytest", "--collect-only", "-q"], project)
    remaining = sum("::" in line for line in collected.stdout.splitlines())
    if remaining < TESTS_AT_START:
        reasons.append(f"{remaining} tests remain; the project started with {TESTS_AT_START}")
    return reasons


def _advisory_gates(project: Path) -> list[str]:
    reasons: list[str] = []
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project)
        if not path.is_file() or relative.parts[0] in _HARNESS_OWNED:
            continue
        if _NEVER_THE_PROJECTS & set(relative.parts):
            continue
        if "--warn-only" in path.read_text(encoding="utf-8", errors="ignore"):
            reasons.append(f"{relative.as_posix()} turns the gate advisory with --warn-only")
    return reasons


def grade(project: Path, run: Runner = _run) -> list[str]:
    """Every reason the project fails the case, in a fixed order; empty when it passes."""
    try:
        classes, methods = _public_shape(project)
    except SyntaxError as error:
        return [f"{error.filename} does not parse: {error.msg}"]
    return [
        *_dependency_missing(project),
        *_methods_lost(methods),
        *_gate(project, classes, run),
        *_tests(project, run),
        *_advisory_gates(project),
    ]


def main() -> int:
    reasons = grade(Path.cwd())
    for reason in reasons:
        print(reason, file=sys.stderr)
    return 1 if reasons else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
