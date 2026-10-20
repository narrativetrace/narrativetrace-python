# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The mutmut copy set in ``evals/pyproject.toml`` covers every module ``run.py`` imports flat.

mutmut copies only ``source_paths`` and ``also_copy`` into ``mutants/``; a runner module missing
from the copy makes ``import run`` fail at collection there (B-105, and Pro 163 before it). This
runs in the ordinary gate, not only under mutmut.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

_EVALS = Path(__file__).resolve().parent


def _mutmut_config() -> dict[str, list[str]]:
    data = tomllib.loads((_EVALS / "pyproject.toml").read_text(encoding="utf-8"))
    config: dict[str, list[str]] = data["tool"]["mutmut"]
    return config


def _flat_imports_of_run() -> set[str]:
    tree = ast.parse((_EVALS / "run.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
    return {name for name in names if (_EVALS / f"{name}.py").is_file()}


def _ignored_tests(config: dict[str, list[str]]) -> set[str]:
    args = config["pytest_add_cli_args"]
    return {a.removeprefix("--ignore=") for a in args if a.startswith("--ignore=")}


def test_run_imports_at_least_one_flat_module() -> None:
    assert {"quota", "case_prompt"} <= _flat_imports_of_run()


def test_every_flat_import_of_run_is_a_mutmut_source_path() -> None:
    sources = set(_mutmut_config()["source_paths"])
    missing = {f"{name}.py" for name in _flat_imports_of_run()} - sources
    assert missing == set()


def test_every_test_of_a_flat_import_is_copied_or_ignored() -> None:
    config = _mutmut_config()
    covered = set(config["also_copy"]) | _ignored_tests(config)
    wanted = {
        f"test_{name}.py"
        for name in _flat_imports_of_run()
        if (_EVALS / f"test_{name}.py").is_file()
    }
    assert wanted - covered == set()
