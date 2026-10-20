# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-93: a case document's ``**Fixture:**`` line and the fixture the runner scaffolds are the same
directory. The runner reads ``case.json`` and otherwise defaults to ``examples/sixty_seconds``; a
document that names another fixture without a ``case.json`` describes a project the agent never
gets -- the case then grades a different world than the one it documents."""

from __future__ import annotations

import re
from pathlib import Path

import case_prompt
import pytest
import run

_EVALS_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _EVALS_DIR.parent
_FIXTURE_LINE = re.compile(r"^\*\*Fixture:\*\*\s+`([^`]+)`", re.MULTILINE)


def _documented_cases() -> list[tuple[str, str, str]]:
    cases = []
    for prompt in sorted(_EVALS_DIR.glob("*/*/prompt.md")):
        if not case_prompt.is_case_document(prompt):
            continue
        match = _FIXTURE_LINE.search(prompt.read_text(encoding="utf-8"))
        if match:
            cases.append((prompt.parent.parent.name, prompt.parent.name, match.group(1)))
    return cases


def _documented_directory(path: str) -> Path:
    """``evals/...`` is relative to the catalogue package, anything else to the repository root."""
    base = _PACKAGE_DIR if path.startswith("evals/") else run._REPO_ROOT
    return (base / path).resolve()


def test_the_cross_check_sees_every_case_document_with_a_fixture_line() -> None:
    assert len(_documented_cases()) == 4


@pytest.mark.parametrize(("skill", "case", "documented"), _documented_cases())
def test_the_documented_fixture_is_the_one_the_runner_scaffolds(
    skill: str, case: str, documented: str
) -> None:
    scaffolded = (run._REPO_ROOT / run._case_fixture(skill, case)).resolve()
    assert scaffolded == _documented_directory(documented), f"{skill}/{case}"
    assert scaffolded.is_dir()
