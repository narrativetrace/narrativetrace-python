# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The version-guard end-to-end test builds its carrier from this checkout, so what the
environment happens to have installed cannot turn it red.

Nightly 2026-10-11 (``poe mutate-gate`` baseline): the container's ``narrativetrace-skills`` was
0.2.0 while ``narrativetrace`` was 0.3.0, and ``TestTheVersionGuardInItsRealSetting`` — which took
"whatever an install here resolves" — saw the mismatch it exists to warn about. This test stages
that environment (a 0.2.0 carrier first on ``PYTHONPATH``) and runs the guard test in it.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - runs this interpreter's pytest on a repository file
import sys
from pathlib import Path

_GUARD = (
    Path(__file__).resolve().parent
    / "test_installer_from_another_package.py::TestTheVersionGuardInItsRealSetting"
)


def _checkout_payload() -> Path:
    for parent in Path(__file__).resolve().parents:
        payload = parent / "packages" / "narrativetrace-skills" / "skills"
        if payload.is_dir():
            return payload
    raise AssertionError("no packages/narrativetrace-skills/skills above this test")


def _stale_carrier(root: Path) -> Path:
    shutil.copytree(_checkout_payload(), root / "skills")
    info = root / "narrativetrace_skills-0.2.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: narrativetrace-skills\nVersion: 0.2.0\n", encoding="utf-8"
    )
    return root


def test_the_guard_test_stays_green_beside_a_stale_installed_carrier(tmp_path: Path) -> None:
    stale = _stale_carrier(tmp_path / "stale")
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(stale), os.environ.get("PYTHONPATH", "")]),
    }

    done = subprocess.run(  # nosec B603 - this interpreter, a test file of this repository
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", str(_GUARD)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )

    assert done.returncode == 0, done.stdout + done.stderr
