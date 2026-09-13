# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakePackageInfo, MakeSnapshot

from narrativetrace.doctor.checks.python_version import check_python_version


class TestCheckPythonVersion:
    def test_passes_when_interpreter_satisfies_the_default_range(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        finding = check_python_version(make_snapshot(python_version="3.12.4"))
        assert finding.status == "pass"

    def test_fails_when_interpreter_is_too_old(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_python_version(make_snapshot(python_version="3.9.0"))
        assert finding.status == "fail"
        assert finding.fix != ""

    def test_reads_the_required_range_from_the_installed_package(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            python_version="3.13.0",
            installed_packages={
                "narrativetrace": package_info("narrativetrace", "0.1.1", ">=3.13")
            },
        )
        assert check_python_version(snapshot).status == "pass"

    def test_fails_against_a_stricter_installed_requirement(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            python_version="3.12.4",
            installed_packages={
                "narrativetrace": package_info("narrativetrace", "0.1.1", ">=3.13")
            },
        )
        assert check_python_version(snapshot).status == "fail"

    def test_id_is_stable(self, make_snapshot: MakeSnapshot) -> None:
        assert check_python_version(make_snapshot()).id == "toolchain.python-version"
