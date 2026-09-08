# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The security-scanner missing-binary gate (`scripts/run_security_tool.py`).

Mirrors a 2026-09-08 audit's finding in the Java spec repo and its fix, `ScannerGateSupport`: a
scanner binary that cannot be resolved must never look like a clean scan. `resolve()`/`main()`'s
network and subprocess glue is exercised for real by `poe secrets-scan` / `poe osv-scan`; these
tests cover the pure decision and status-recording logic in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.run_security_tool import (
    decide_missing_binary,
    record_ran_clean,
    record_skipped,
    scan_status,
    security_scanners_required,
)


class TestDecideMissingBinary:
    def test_fails_outright_when_scanners_are_required(self) -> None:
        decision = decide_missing_binary("gitleaks", required=True)

        assert decision.fail is True
        assert "gitleaks" in decision.message
        assert "required" in decision.message

    def test_warns_loudly_when_scanners_are_not_required(self) -> None:
        decision = decide_missing_binary("osv-scanner", required=False)

        assert decision.fail is False
        assert "SKIPPED" in decision.message
        assert "NOT a clean scan" in decision.message


class TestSecurityScannersRequired:
    def test_false_with_neither_env_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("NARRATIVETRACE_SECURITY_REQUIRED", raising=False)

        assert security_scanners_required() is False

    def test_true_when_ci_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("NARRATIVETRACE_SECURITY_REQUIRED", raising=False)

        assert security_scanners_required() is True

    def test_true_when_the_explicit_flag_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("NARRATIVETRACE_SECURITY_REQUIRED", "true")

        assert security_scanners_required() is True

    def test_an_empty_ci_value_does_not_count_as_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # GitLab/GitHub Actions runners set CI to a truthy string; a locally exported-but-empty
        # CI must not accidentally flip a developer machine into required mode.
        monkeypatch.setenv("CI", "")
        monkeypatch.delenv("NARRATIVETRACE_SECURITY_REQUIRED", raising=False)

        assert security_scanners_required() is False


class TestScanStatus:
    def test_a_scan_that_never_ran_reports_never_ran(self, tmp_path: Path) -> None:
        assert scan_status(tmp_path, "gitleaks") == "never-ran"

    def test_a_recorded_skip_is_distinguishable_from_a_clean_run(self, tmp_path: Path) -> None:
        record_skipped(tmp_path, "gitleaks", "binary not on PATH")

        status = scan_status(tmp_path, "gitleaks")
        assert status.startswith("skipped")
        assert "binary not on PATH" in status

    def test_a_clean_run_is_recorded_as_ran_clean(self, tmp_path: Path) -> None:
        record_ran_clean(tmp_path, "osv-scanner")

        assert scan_status(tmp_path, "osv-scanner") == "ran-clean"

    def test_a_later_clean_run_replaces_an_earlier_skip(self, tmp_path: Path) -> None:
        record_skipped(tmp_path, "osv-scanner", "binary not on PATH")
        record_ran_clean(tmp_path, "osv-scanner")

        assert scan_status(tmp_path, "osv-scanner") == "ran-clean"

    def test_each_tool_has_its_own_status(self, tmp_path: Path) -> None:
        record_ran_clean(tmp_path, "gitleaks")
        record_skipped(tmp_path, "semgrep", "binary not on PATH")

        assert scan_status(tmp_path, "gitleaks") == "ran-clean"
        assert scan_status(tmp_path, "semgrep").startswith("skipped")
