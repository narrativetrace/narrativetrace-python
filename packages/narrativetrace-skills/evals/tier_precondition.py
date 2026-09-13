# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Sporadic-lanes policy: "Deterministic tiers first, always. A cheaper-lane run refuses to start
unless the skill's Tier A lints and Tier A2 replay are green at HEAD — a Tier B trial on a skill
whose replay is red is quota burned on a known defect." ``run`` is injectable so a unit test can
fake the command without a real pytest run.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

RunCommand = Callable[[Sequence[str], str], None]


def run_command(args: Sequence[str], cwd: str) -> None:
    subprocess.run(  # nosec B603, B607 # fixed argv (uv/pytest + a literal path), no shell
        list(args), cwd=cwd, capture_output=True, check=True
    )


_TIER_A_AND_A2_FILES = (
    "packages/narrativetrace-skills/tests/test_catalogue_lints.py",
    "packages/narrativetrace-skills/tests/test_replay_fixture.py",
)


def assert_deterministic_tiers_green(repo_root: str, run: RunCommand = run_command) -> None:
    """Raises, with a quota-preserving explanation, when the skills package's Tier A/A2 suite is
    red."""
    try:
        run(["uv", "run", "pytest", *_TIER_A_AND_A2_FILES], repo_root)
    except Exception as error:
        raise RuntimeError(
            "Tier A lints / Tier A2 replay are not green at HEAD for narrativetrace-skills -- a "
            "sporadic-lane (codex/gemini) trial refuses to start on top of a known defect. Fix "
            "packages/narrativetrace-skills' own tests before spending quota here."
        ) from error
