# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakeSnapshot

from narrativetrace.doctor.checks.parameter_names import check_parameter_names


class TestCheckParameterNames:
    def test_passes_with_no_rendered_output(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_parameter_names(make_snapshot())
        assert finding.status == "pass"
        assert "no rendered output" in finding.message

    def test_passes_when_output_carries_real_names(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(output_files={"T/m.md": "Calc.add(a: 1, b: 2) → 3"})
        assert check_parameter_names(snapshot).status == "pass"

    def test_fails_when_output_shows_a_collapsed_args_capture(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(output_files={"T/m.md": "Calc.add(args: [1, 2]) → 3"})
        finding = check_parameter_names(snapshot)
        assert finding.status == "fail"
        assert "T/m.md" in finding.message
        assert "@traced" in finding.fix
