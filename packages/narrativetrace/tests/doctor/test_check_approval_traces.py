# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakeSnapshot

from narrativetrace.doctor.checks.approval_traces import check_approval_traces


class TestCheckApprovalTraces:
    def test_passes_with_no_approved_dir_files(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_approval_traces(make_snapshot())
        assert finding.status == "pass"
        assert "nothing to check" in finding.message

    def test_passes_with_only_approved_traces(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(approved_dir_files={"T/m.approved.nt": "scenario: s\n"})
        finding = check_approval_traces(snapshot)
        assert finding.status == "pass"
        assert "1 approved trace(s)" in finding.message

    def test_fails_when_a_received_trace_is_present(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            approved_dir_files={
                "T/m.approved.nt": "scenario: s\n",
                "T/m.received.nt": "scenario: s\n\n- A.b()\n",
            }
        )
        finding = check_approval_traces(snapshot)
        assert finding.status == "fail"
        assert "T/m.received.nt" in finding.message
        assert "narrativetrace-approve" in finding.fix

    def test_names_every_received_trace(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            approved_dir_files={"T/a.received.nt": "x", "T/b.received.nt": "y"}
        )
        finding = check_approval_traces(snapshot)
        assert "T/a.received.nt" in finding.message
        assert "T/b.received.nt" in finding.message

    def test_ignores_incomplete_traces(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(approved_dir_files={"T/m.incomplete.nt": "scenario: s\n"})
        finding = check_approval_traces(snapshot)
        assert finding.status == "pass"
        assert "0 approved trace(s)" in finding.message
