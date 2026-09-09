# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The formatter/linter skip-vs-clean gate (`scripts/quality_gate_status.py`).

Mirrors `scripts/run_security_tool.py`'s missing-binary gate: a formatter or linter that can't run
must never look like a clean check. `main()`'s CLI glue is exercised by the pre-commit hook
actually running, not here — these tests cover the pure decision and status-recording logic in
isolation, exactly like `test_run_security_tool.py` and `test_mutation_gate.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.quality_gate_status import (
    decide_missing_tool,
    quality_checks_required,
    quality_status,
    record_ran_clean,
    record_skipped,
)


class TestDecideMissingTool:
    def test_fails_outright_when_quality_checks_are_required(self) -> None:
        decision = decide_missing_tool("formatter", required=True)

        assert decision.fail is True
        assert "formatter" in decision.message
        assert "required" in decision.message

    def test_warns_loudly_when_quality_checks_are_not_required(self) -> None:
        decision = decide_missing_tool("linter", required=False)

        assert decision.fail is False
        assert "SKIPPED" in decision.message
        assert "NOT a clean check" in decision.message


class TestQualityChecksRequired:
    def test_false_with_neither_env_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("NARRATIVETRACE_QUALITY_REQUIRED", raising=False)

        assert quality_checks_required() is False

    def test_true_when_ci_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("NARRATIVETRACE_QUALITY_REQUIRED", raising=False)

        assert quality_checks_required() is True

    def test_true_when_the_explicit_flag_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("NARRATIVETRACE_QUALITY_REQUIRED", "true")

        assert quality_checks_required() is True

    def test_an_empty_ci_value_does_not_count_as_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # GitLab/GitHub Actions runners set CI to a truthy string; a locally exported-but-empty
        # CI must not accidentally flip a developer machine into required mode.
        monkeypatch.setenv("CI", "")
        monkeypatch.delenv("NARRATIVETRACE_QUALITY_REQUIRED", raising=False)

        assert quality_checks_required() is False


class TestQualityStatus:
    def test_a_check_that_never_ran_reports_never_ran(self, tmp_path: Path) -> None:
        assert quality_status(tmp_path, "formatter") == "never-ran"

    def test_a_recorded_skip_is_distinguishable_from_a_clean_run(self, tmp_path: Path) -> None:
        record_skipped(tmp_path, "formatter", "formatter unavailable or errored")

        status = quality_status(tmp_path, "formatter")
        assert status.startswith("skipped")
        assert "formatter unavailable or errored" in status

    def test_a_clean_run_is_recorded_as_ran_clean(self, tmp_path: Path) -> None:
        record_ran_clean(tmp_path, "linter")

        assert quality_status(tmp_path, "linter") == "ran-clean"

    def test_a_later_clean_run_replaces_an_earlier_skip(self, tmp_path: Path) -> None:
        record_skipped(tmp_path, "linter", "linter unavailable")
        record_ran_clean(tmp_path, "linter")

        assert quality_status(tmp_path, "linter") == "ran-clean"

    def test_each_tool_has_its_own_status(self, tmp_path: Path) -> None:
        record_ran_clean(tmp_path, "formatter")
        record_skipped(tmp_path, "linter", "linter unavailable")

        assert quality_status(tmp_path, "formatter") == "ran-clean"
        assert quality_status(tmp_path, "linter").startswith("skipped")
