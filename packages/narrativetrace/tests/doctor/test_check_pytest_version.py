# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakePackageInfo, MakeSnapshot

from narrativetrace.doctor.checks.pytest_version import check_pytest_version


class TestCheckPytestVersion:
    def test_passes_when_narrativetrace_pytest_is_not_installed(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        finding = check_pytest_version(make_snapshot())
        assert finding.status == "pass"

    def test_passes_when_installed_pytest_satisfies_the_declared_range(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace-pytest": package_info(
                    "narrativetrace-pytest", "0.1.1", requires=("pytest>=8",)
                ),
                "pytest": package_info("pytest", "9.1.1"),
            }
        )
        assert check_pytest_version(snapshot).status == "pass"

    def test_fails_when_pytest_is_not_installed_at_all(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace-pytest": package_info(
                    "narrativetrace-pytest", "0.1.1", requires=("pytest>=8",)
                )
            }
        )
        finding = check_pytest_version(snapshot)
        assert finding.status == "fail"
        assert "no pytest install was found" in finding.message

    def test_fails_when_installed_pytest_is_too_old(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace-pytest": package_info(
                    "narrativetrace-pytest", "0.1.1", requires=("pytest>=8",)
                ),
                "pytest": package_info("pytest", "7.4.0"),
            }
        )
        finding = check_pytest_version(snapshot)
        assert finding.status == "fail"
        assert finding.fix != ""
