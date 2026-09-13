# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakePackageInfo, MakeSnapshot

from narrativetrace.doctor.doctor import DOCTOR_CHECKS, run_doctor


class TestDoctorChecks:
    def test_eleven_checks_registered(self) -> None:
        assert len(DOCTOR_CHECKS) == 11

    def test_every_check_id_is_unique(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot()
        ids = [check(snapshot).id for check in DOCTOR_CHECKS]
        assert len(ids) == len(set(ids))

    def test_every_check_id_is_dotted(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot()
        for check in DOCTOR_CHECKS:
            assert "." in check(snapshot).id


class TestRunDoctor:
    def test_exit_code_zero_when_everything_passes(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace": package_info("narrativetrace", "0.1.1", requires_python=">=3.12")
            },
            source_files={"tests/test_service.py": "assert result == '[REDACTED]'"},
        )
        report = run_doctor(snapshot)
        assert report.exit_code == 0
        assert len(report.findings) == 11

    def test_exit_code_one_when_any_finding_fails(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(python_version="3.9.0")
        report = run_doctor(snapshot)
        assert report.exit_code == 1

    def test_findings_preserve_check_order(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot()
        report = run_doctor(snapshot)
        ids = [finding.id for finding in report.findings]
        assert ids[0] == "toolchain.python-version"
        assert ids[-1] == "trap.llms-before-you-start"
