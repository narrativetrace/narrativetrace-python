# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakePackageInfo, MakeSnapshot

from narrativetrace_tooling.doctor.doctor import DOCTOR_CHECKS, run_doctor
from narrativetrace_tooling.doctor.finding_skills import knows
from narrativetrace_tooling.frameworks.table import wiring_check_ids


class TestDoctorChecks:
    def test_nineteen_checks_registered(self) -> None:
        assert len(DOCTOR_CHECKS) == 19

    def test_one_check_per_framework_table_row_follows_the_thirteen_core_checks(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """Phase 6 D3: the registry derives the framework checks from the table, in table order,
        appended after the core checks so no shipped id moves."""
        snapshot = make_snapshot()
        ids = tuple(check(snapshot).id for check in DOCTOR_CHECKS)
        assert ids[13:] == wiring_check_ids()

    def test_every_check_id_is_unique(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot()
        ids = [check(snapshot).id for check in DOCTOR_CHECKS]
        assert len(ids) == len(set(ids))

    def test_every_check_id_is_dotted(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot()
        for check in DOCTOR_CHECKS:
            assert "." in check(snapshot).id

    def test_every_registered_check_has_a_skill_decision(self, make_snapshot: MakeSnapshot) -> None:
        """A check that ships with no row in the skill table is a check nobody decided a skill
        for — a decided ``None`` (:mod:`~narrativetrace_tooling.doctor.finding_skills`'s
        ``_NO_SKILL``) is a different thing and must still be listed there."""
        snapshot = make_snapshot()
        for check in DOCTOR_CHECKS:
            check_id = check(snapshot).id
            assert knows(check_id), f"no skill decision for {check_id}"


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
        assert len(report.findings) == 19

    def test_exit_code_one_when_any_finding_fails(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(python_version="3.9.0")
        report = run_doctor(snapshot)
        assert report.exit_code == 1

    def test_findings_preserve_check_order(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot()
        report = run_doctor(snapshot)
        ids = [finding.id for finding in report.findings]
        assert ids[0] == "toolchain.python-version"
        assert ids[11] == "trap.llms-before-you-start"
        assert ids[12] == "config.approval-mode"
        assert ids[-1] == "config.django-integration"
        assert ids[5] == "config.skills-installed"
