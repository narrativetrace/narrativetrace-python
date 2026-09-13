# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakeSnapshot

from narrativetrace.doctor.checks.unknown_config_keys import check_unknown_config_keys


class TestCheckUnknownConfigKeys:
    def test_passes_with_no_config_file(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_unknown_config_keys(make_snapshot())
        assert finding.status == "pass"

    def test_passes_when_every_key_is_known(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(narrativetrace_config={"level": "DETAIL", "output_dir": "traces"})
        assert check_unknown_config_keys(snapshot).status == "pass"

    def test_fails_on_a_typo_d_key(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(narrativetrace_config={"ouput_dir": "traces"})
        finding = check_unknown_config_keys(snapshot)
        assert finding.status == "fail"
        assert "ouput_dir" in finding.message

    def test_names_every_unknown_key(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(narrativetrace_config={"ouput_dir": "x", "aproved_dir": "y"})
        finding = check_unknown_config_keys(snapshot)
        assert "aproved_dir" in finding.message
        assert "ouput_dir" in finding.message
