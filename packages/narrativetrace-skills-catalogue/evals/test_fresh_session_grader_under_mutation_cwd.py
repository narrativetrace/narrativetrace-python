# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests that read case content must collect where mutmut runs them, not only beside the graders.

``poe mutate-skills`` copies every ``test*.py`` into ``evals/mutants/`` and runs pytest there; the
case directories (graders) are not copied, so the test has to find them one level up. Nightly
2026-10-11: ``ModuleNotFoundError: grade_the_fresh_session`` under that cwd. This file is itself
excluded from the mutation run (``--ignore`` in ``pyproject.toml``): it simulates the copy.
"""

from __future__ import annotations

import subprocess  # nosec B404 - runs this interpreter's pytest on a repository file
import sys
from pathlib import Path

import pytest

_EVALS = Path(__file__).resolve().parent
_CASE_DIRS = ("add-narrative-tracing", "narrativetrace-feedback")
# Copied by mutmut and run from the copy, yet reading case content beside themselves.
_COPIED_TESTS = ("test_fresh_session_grader.py", "test_bounded.py", "test_run.py")


@pytest.mark.parametrize("test_file", _COPIED_TESTS)
def test_the_test_collects_and_passes_from_a_mutants_copy(tmp_path: Path, test_file: str) -> None:
    evals = tmp_path / "evals"
    mutants = evals / "mutants"
    mutants.mkdir(parents=True)
    for name in _CASE_DIRS:
        (evals / name).symlink_to(_EVALS / name, target_is_directory=True)
    for module in _EVALS.glob(
        "*.py"
    ):  # the runner modules mutmut mutates and copies beside the tests
        if not module.name.startswith("test"):
            (mutants / module.name).write_bytes(module.read_bytes())
    copy = mutants / test_file
    copy.write_bytes((_EVALS / test_file).read_bytes())

    done = subprocess.run(  # nosec B603 - this interpreter, a file copied from this repository
        [sys.executable, "-m", "pytest", "-p", "no:narrativetrace", "-q", copy.name],
        cwd=mutants,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )

    assert done.returncode == 0, done.stdout + done.stderr
