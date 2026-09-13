# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakePackageInfo, MakeSnapshot

from narrativetrace.doctor.checks.pytest_plugin_registered import check_pytest_plugin_registered


class TestCheckPytestPluginRegistered:
    def test_passes_when_narrativetrace_pytest_is_not_installed(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        finding = check_pytest_plugin_registered(make_snapshot())
        assert finding.status == "pass"

    def test_passes_when_registered_and_not_disabled(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace-pytest": package_info("narrativetrace-pytest", "0.1.1")
            },
            pytest11_entry_points={"narrativetrace": "narrativetrace_pytest.plugin"},
        )
        assert check_pytest_plugin_registered(snapshot).status == "pass"

    def test_fails_when_entry_point_is_missing(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace-pytest": package_info("narrativetrace-pytest", "0.1.1")
            },
            pytest11_entry_points={},
        )
        finding = check_pytest_plugin_registered(snapshot)
        assert finding.status == "fail"
        assert "no" in finding.message and "entry point" in finding.message

    def test_fails_when_entry_point_resolves_elsewhere(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace-pytest": package_info("narrativetrace-pytest", "0.1.1")
            },
            pytest11_entry_points={"narrativetrace": "something_else.plugin"},
        )
        finding = check_pytest_plugin_registered(snapshot)
        assert finding.status == "fail"
        assert "something_else.plugin" in finding.message

    def test_fails_when_addopts_disables_the_plugin(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace-pytest": package_info("narrativetrace-pytest", "0.1.1")
            },
            pytest11_entry_points={"narrativetrace": "narrativetrace_pytest.plugin"},
            source_files={"pyproject.toml": "addopts = '-p no:narrativetrace'"},
        )
        finding = check_pytest_plugin_registered(snapshot)
        assert finding.status == "fail"
        assert "pyproject.toml" in finding.message

    def test_passes_when_a_different_plugin_is_disabled(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            installed_packages={
                "narrativetrace-pytest": package_info("narrativetrace-pytest", "0.1.1")
            },
            pytest11_entry_points={"narrativetrace": "narrativetrace_pytest.plugin"},
            source_files={"pyproject.toml": "addopts = '-p no:cacheprovider'"},
        )
        assert check_pytest_plugin_registered(snapshot).status == "pass"
