# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tier_precondition import assert_deterministic_tiers_green, run_command


class TestRunCommand:
    def test_runs_a_successful_command(self, tmp_path: Path) -> None:
        run_command(["true"], str(tmp_path))  # must not raise

    def test_raises_on_a_nonzero_exit(self, tmp_path: Path) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            run_command(["false"], str(tmp_path))


class TestAssertDeterministicTiersGreen:
    def test_passes_silently_when_run_succeeds(self) -> None:
        assert_deterministic_tiers_green("/repo", run=lambda args, cwd: None)

    def test_raises_a_quota_preserving_explanation_when_run_fails(self) -> None:
        def _failing(args: object, cwd: str) -> None:
            raise RuntimeError("suite is red")

        with pytest.raises(RuntimeError, match="refuses to start"):
            assert_deterministic_tiers_green("/repo", run=_failing)

    def test_chains_the_original_failure_as_the_cause(self) -> None:
        original = RuntimeError("suite is red")

        def _failing(args: object, cwd: str) -> None:
            raise original

        with pytest.raises(RuntimeError) as excinfo:
            assert_deterministic_tiers_green("/repo", run=_failing)
        assert excinfo.value.__cause__ is original

    def test_passes_the_repo_root_as_cwd(self) -> None:
        seen: dict[str, object] = {}

        def _capture(args: object, cwd: str) -> None:
            seen["cwd"] = cwd

        assert_deterministic_tiers_green("/my-repo", run=_capture)
        assert seen["cwd"] == "/my-repo"
