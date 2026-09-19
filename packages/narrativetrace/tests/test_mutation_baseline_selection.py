# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The mutation baseline must not build wheels.

mutmut's `pytest_add_cli_args_test_selection` is the argument list `PytestRunner` falls back to
whenever no specific killer tests have been narrowed down yet — that covers the clean-tests
baseline, the stats-collection pass and the forced-fail check alike. A distribution test that
builds real wheels (`built_distributions` in `test_distribution_licensing.py` shells out to
`uv build`) can never reach the network for a build-backend wheel that is not already in the
local cache once the outer run is offline, so a cold-cache runner fails every one of them. Such a
test proves packaging, not code under mutation, and has no place in that selection; the ordinary
test suite still runs it.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

NARRATIVETRACE_DIR = Path(__file__).resolve().parent.parent
_MUTMUT_CONFIG = tomllib.loads((NARRATIVETRACE_DIR / "pyproject.toml").read_text(encoding="utf-8"))[
    "tool"
]["mutmut"]


class TestTheBaselineSelectionDeselectsDistributionTests:
    def test_the_test_selection_args_deselect_the_distribution_marker(self) -> None:
        """`-m` is a single-valued pytest option — a second `-m` wins outright over the root
        addopts' own `-m "not stress"` rather than combining with it, so whatever this config adds
        must restate every marker exclusion that already applies, not just the new one."""
        args = _MUTMUT_CONFIG["pytest_add_cli_args_test_selection"]
        assert "-m" in args, args
        expression = args[args.index("-m") + 1]
        assert "not distribution" in expression
        assert "not stress" in expression

    def test_the_selection_actually_collects_no_distribution_tests(self) -> None:
        """Proves the deselection against a real pytest collection, not just the config text."""
        collected = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                *_MUTMUT_CONFIG["pytest_add_cli_args_test_selection"],
            ],
            cwd=NARRATIVETRACE_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        assert collected.returncode == 0, collected.stdout + collected.stderr
        assert "TestEveryBuiltArtifact" not in collected.stdout
