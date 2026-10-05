# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Helpers for the suites that test the REAL built distributions rather than the source tree.

Two suites need them — what a wheel carries, and what the console script inside one does once
installed — so they live beside the tests as a support module, the same shape `stress_support.py`
already has. The session-scoped `built_wheels` fixture that uses `build_wheels` is in `conftest.py`,
because that is the only place a session fixture is shared from.

Every child process started from here runs in a CONSUMER's environment (`consumer_environment`), not
this test session's: see that function for what leaks otherwise, and why it matters twice over.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

_SESSION_ONLY_VARIABLES = ("COVERAGE_PROCESS_START", "COVERAGE_FILE", "PYTHONPATH")


def consumer_environment() -> dict[str, str]:
    """This process's environment with the test session's own bootstrap removed.

    `packages/narrativetrace-pytest/tests/conftest.py` sets `COVERAGE_PROCESS_START`,
    `COVERAGE_FILE` and a `PYTHONPATH` carrying its `sitecustomize` for the WHOLE session (it has
    to: its own subprocesses are the code it measures). Children started from here inherit that,
    which is wrong in both directions — a build backend or an installed console script would start
    measuring coverage into this repository's data file, and an interpreter that has no `coverage`
    installed (a venv made from the built wheels alone) fails to import the `sitecustomize` it was
    pointed at. A suite that asks "does the real artifact work for a consumer" has to ask it in a
    consumer's environment.
    """
    return {
        name: value for name, value in os.environ.items() if name not in _SESSION_ONLY_VARIABLES
    }


def repo_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories: mutmut runs this
    suite from a `packages/narrativetrace/mutants/` copy, one level deeper than the source tree."""
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


def wheel_name(distribution_dir: str) -> str:
    """The wheel file name `uv build` writes for one workspace member (PEP 427/503 naming)."""
    project = _read_toml(repo_root() / "packages" / distribution_dir / "pyproject.toml")["project"]
    canonical = re.sub(r"[-_.]+", "_", str(project["name"])).lower()
    return f"{canonical}-{project['version']}-py3-none-any.whl"


def build_wheels(out_dir: Path) -> Path:
    """Builds every workspace member's real wheel and sdist into `out_dir`, and returns it.

    Skips the calling test when `uv` is not on PATH: without it there is no artifact to look at, and
    a green run that inspected nothing would be worse than a skipped one.
    """
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH, so the built wheels cannot be inspected")
    build = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        ["uv", "build", "--all-packages", "--out-dir", str(out_dir)],
        cwd=repo_root(),
        env=consumer_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, f"uv build failed:\n{build.stdout}\n{build.stderr}"
    return out_dir


def _read_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))
