# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakePackageInfo, MakeSnapshot

from narrativetrace.doctor.checks.llms_before_you_start import check_llms_before_you_start


class TestCheckLlmsBeforeYouStart:
    def test_passes_when_structlog_bridge_is_not_used(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_llms_before_you_start(make_snapshot())
        assert finding.status == "pass"

    def test_passes_when_structlog_resolves(
        self, make_snapshot: MakeSnapshot, package_info: MakePackageInfo
    ) -> None:
        snapshot = make_snapshot(
            source_files={"app.py": "from narrativetrace_structlog import processor"},
            installed_packages={"structlog": package_info("structlog", "24.1.0")},
        )
        assert check_llms_before_you_start(snapshot).status == "pass"

    def test_fails_when_structlog_does_not_resolve(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            source_files={"app.py": "from narrativetrace_structlog import processor"}
        )
        finding = check_llms_before_you_start(snapshot)
        assert finding.status == "fail"
        assert "uv add structlog" in finding.fix

    def test_ignores_non_python_files(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(source_files={"notes.md": "narrativetrace_structlog"})
        assert check_llms_before_you_start(snapshot).status == "pass"
