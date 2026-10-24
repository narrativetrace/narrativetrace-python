# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""No test may locate the repository by counting parents of ``__file__``.

Under ``mutmut`` the suite re-runs from a copied tree one level deeper
(``packages/narrativetrace/mutants/tests/``), so ``Path(__file__).resolve().parents[3]`` lands on
``packages/`` and every docs-reading test dies with ``FileNotFoundError`` -- which aborts the
stats-collection phase and the whole mutation gate (nightly 2026-10-22, B-153). A test finds the
workspace root by walking up to the directory holding ``pyproject.toml`` and ``packages/``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTS = Path(__file__).resolve().parent


def _fixed_depth_parents_uses(source: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, int)
    ]


def test_no_test_module_counts_parents_to_find_the_repository() -> None:
    offenders = {
        path.name: lines
        for path in sorted(_TESTS.glob("*.py"))
        if (lines := _fixed_depth_parents_uses(path.read_text(encoding="utf-8")))
    }
    assert not offenders, offenders


def test_the_detector_flags_a_fixed_depth_parent_lookup() -> None:
    assert _fixed_depth_parents_uses("x = Path(__file__).resolve().parents[3] / 'a'") == [1]
    assert _fixed_depth_parents_uses("for c in Path(__file__).resolve().parents: pass") == []
