# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakePackageInfo, MakeSnapshot

from narrativetrace.doctor.checks.package_versions import check_package_versions


class TestCheckPackageVersions:
    def test_passes_with_fewer_than_two_installed(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={"narrativetrace": package_info("narrativetrace", "0.1.1")}
        )
        finding = check_package_versions(snapshot)
        assert finding.status == "pass"
        assert "nothing to compare" in finding.message

    def test_passes_when_every_installed_package_agrees(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace": package_info("narrativetrace", "0.1.1"),
                "narrativetrace-pytest": package_info("narrativetrace-pytest", "0.1.1"),
            }
        )
        assert check_package_versions(snapshot).status == "pass"

    def test_fails_when_versions_disagree(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace": package_info("narrativetrace", "0.1.1"),
                "narrativetrace-pytest": package_info("narrativetrace-pytest", "0.1.0"),
            }
        )
        finding = check_package_versions(snapshot)
        assert finding.status == "fail"
        assert "narrativetrace==0.1.1" in finding.message
        assert "narrativetrace-pytest==0.1.0" in finding.message

    def test_ignores_packages_outside_the_eight(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace": package_info("narrativetrace", "0.1.1"),
                "pytest": package_info("pytest", "9.1.1"),
            }
        )
        finding = check_package_versions(snapshot)
        assert finding.status == "pass"
        assert "nothing to compare" in finding.message
