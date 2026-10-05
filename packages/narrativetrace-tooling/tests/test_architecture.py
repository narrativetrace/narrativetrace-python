# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The two halves of the tooling library's zero-dependency contract, as a test rather than a
comment.

Java pins the same rule with ArchUnit (``narrativetrace-tooling``'s own ``ArchitectureTest``): a
library both entry points embed may never reach back into either of them, and it never links against
the runtime it diagnoses. Python has no compile step to catch it, and a single convenience import of
``narrativetrace`` here would turn the dependency edge the ``narrativetrace`` console script relies
on into a cycle — one that ``uv`` would happily install and that would only surface as an import
error in somebody's project. So the rule is read straight off the source with :mod:`ast`.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path


def _workspace_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories.

    Load-bearing here, not just tidy: mutmut re-runs this suite from its own ``mutants/tests/``
    copy, and the sources beside it are mutmut's copies — every one of which imports ``mutmut`` for
    its trampoline. A relative ``parents[1]`` would point this sweep at that copy and fail on an
    import the real library does not have.
    """
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


PACKAGE_ROOT = _workspace_root() / "packages" / "narrativetrace-tooling"
SOURCE_ROOT = PACKAGE_ROOT / "src" / "narrativetrace_tooling"

OWN_PACKAGE = "narrativetrace_tooling"


def imported_roots(source: str, filename: str = "<source>") -> list[tuple[str, int]]:
    """Every top-level module name ``source`` imports, with the line it is imported on, in line
    order.

    A relative import (``from . import x``) names nothing outside the package and is skipped:
    ``node.module`` is ``None`` or a submodule path, and ``node.level`` says it is our own.
    """
    tree = ast.parse(source, filename=filename)
    names: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend((alias.name.split(".", 1)[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append((node.module.split(".", 1)[0], node.lineno))
    return sorted(names, key=lambda pair: pair[1])


def _modules() -> list[Path]:
    """Every module in the library — sorted, so a failure names the same file every run."""
    return sorted(SOURCE_ROOT.rglob("*.py"))


def _offences(forbidden: frozenset[str] | None = None) -> list[str]:
    """``<file>:<line> imports <name>`` for every import this library is not allowed to make.

    With no ``forbidden`` set that means anything but the standard library and the library itself;
    with one, exactly the names in it. The root module name is compared EXACTLY, never by prefix:
    ``narrativetrace_tooling`` shares its first 15 characters with the runtime it must not import.
    """
    offences: list[str] = []
    for module in _modules():
        relative = module.relative_to(PACKAGE_ROOT)
        for name, line in imported_roots(module.read_text(encoding="utf-8"), str(relative)):
            allowed = (
                name not in forbidden
                if forbidden is not None
                else name == OWN_PACKAGE or name in sys.stdlib_module_names
            )
            if not allowed:
                offences.append(f"{relative}:{line} imports {name}")
    return offences


class TestTheLibraryTakesNoDependencies:
    def test_the_distribution_declares_no_dependencies(self) -> None:
        metadata = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        assert metadata["project"]["dependencies"] == [], (
            "narrativetrace-tooling is the zero-dependency library both entry points embed; a "
            "dependency here reaches every consumer of the narrativetrace distribution"
        )

    def test_no_module_imports_anything_but_the_standard_library_and_itself(self) -> None:
        assert _offences() == [], (
            "narrativetrace-tooling is standard library only — see its pyproject.toml's own note "
            "on why (a dependency edge here would become a cycle through the console script)"
        )

    def test_no_module_imports_the_runtime_it_diagnoses(self) -> None:
        """The half of the rule that a growing standard library could never relax. Stated
        separately from the sweep above so a failure names the actual mistake: importing
        ``narrativetrace`` reads as harmless, and it is the one import that closes the cycle."""
        assert _offences(forbidden=frozenset({"narrativetrace"})) == [], (
            "narrativetrace_tooling must never import narrativetrace: the narrativetrace "
            "distribution depends on THIS one, so the edge would be a cycle. Read a project as "
            "text, and a carrier through importlib.metadata"
        )

    def test_the_reader_sees_every_import_form_including_the_near_miss_name(self) -> None:
        """A sweep over source that happens to be clean proves nothing about the sweep. The
        near-miss matters twice over: ``narrativetrace_toolingx`` is not this package, and
        ``narrativetrace`` is the forbidden one — a prefix comparison would get both wrong."""
        source = (
            "import narrativetrace_toolingx\n"
            "import json, sys\n"
            "from narrativetrace import config\n"
            "from . import sibling\n"
            "from narrativetrace_tooling.init import carrier\n"
        )

        assert imported_roots(source) == [
            ("narrativetrace_toolingx", 1),
            ("json", 2),
            ("sys", 2),
            ("narrativetrace", 3),
            ("narrativetrace_tooling", 5),
        ]
