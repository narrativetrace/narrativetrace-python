# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import pytest
from snapshot_factory_types import MakeSnapshot

from narrativetrace.doctor.checks.output_env import check_output_env


class TestCheckOutputEnv:
    def test_passes_when_unset(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_output_env(make_snapshot())
        assert finding.status == "pass"
        assert "not set" in finding.message

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " On "])
    def test_passes_on_a_recognized_truthy_spelling(
        self, make_snapshot: MakeSnapshot, value: str
    ) -> None:
        finding = check_output_env(make_snapshot(env={"NARRATIVETRACE_OUTPUT": value}))
        assert finding.status == "pass"
        assert "output is on" in finding.message

    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off"])
    def test_passes_on_a_recognized_falsy_spelling(
        self, make_snapshot: MakeSnapshot, value: str
    ) -> None:
        finding = check_output_env(make_snapshot(env={"NARRATIVETRACE_OUTPUT": value}))
        assert finding.status == "pass"
        assert "output is off" in finding.message

    @pytest.mark.parametrize("value", ["enable", "y", "please", "1.0"])
    def test_fails_on_an_unrecognized_spelling(
        self, make_snapshot: MakeSnapshot, value: str
    ) -> None:
        finding = check_output_env(make_snapshot(env={"NARRATIVETRACE_OUTPUT": value}))
        assert finding.status == "fail"
        assert finding.fix != ""


# The truthy-set parity test against narrativetrace_pytest's own private `_TRUTHY` lives in
# packages/narrativetrace-pytest/tests/test_doctor_truthy_parity.py, not here: the core
# distribution's tests never import an integration package (the same layering rule
# import-linter enforces for source, kept for tests as a matter of direction, not just gate
# reach) -- the higher layer imports down to compare, never the reverse.
