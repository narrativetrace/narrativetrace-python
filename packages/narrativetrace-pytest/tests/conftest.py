# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Wires coverage.py's subprocess-measurement recipe for this package's own test session.

Every test here drives the plugin through ``pytester.runpytest_subprocess()`` -- a real child
``python -m pytest`` process -- never in-process (verified: no test in this package calls
``runpytest``/``runpytest_inprocess``). ``Pytester.popen()`` copies the *current* environment for
every child it spawns, so setting these two variables once, for this test session, reaches every
subprocess every test here creates.

``_subprocess_coverage/sitecustomize.py`` does the actual measuring, once the child interpreter's
``site`` module imports it off ``PYTHONPATH`` at start-up and it sees ``COVERAGE_PROCESS_START``.
"""

from __future__ import annotations

import os
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parents[2]
_SITECUSTOMIZE_DIR = _HERE / "_subprocess_coverage"


def pytest_configure(config: object) -> None:
    os.environ["COVERAGE_PROCESS_START"] = str(_REPO_ROOT / "pyproject.toml")
    os.environ["COVERAGE_FILE"] = str(_REPO_ROOT / ".coverage")
    os.environ["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(_SITECUSTOMIZE_DIR), os.environ.get("PYTHONPATH", "")])
    )
