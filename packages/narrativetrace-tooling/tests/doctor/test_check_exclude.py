# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakeSnapshot

from narrativetrace_tooling.doctor.checks.exclude import ID, check_exclude


class TestCheckExclude:
    def test_the_check_has_a_stable_dotted_id(self) -> None:
        assert ID == "config.exclude"

    def test_reports_the_shipped_default_list_verbatim(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(effective_exclude=("unittest", "pytest"), exclude_source="default")
        finding = check_exclude(snapshot)
        assert finding.status == "pass"
        assert finding.message == (
            "effective exclude list is the shipped default (2 modules): unittest, pytest"
        )

    def test_reports_a_configured_list_and_says_it_replaced_the_default(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(effective_exclude=("acme.mocks",), exclude_source="configured")
        assert check_exclude(snapshot).message == (
            "effective exclude list is configured, replacing the shipped default "
            "(1 module): acme.mocks"
        )

    def test_reports_an_empty_configured_list_as_excluding_nothing(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(effective_exclude=(), exclude_source="configured")
        finding = check_exclude(snapshot)
        assert finding.status == "pass"
        assert finding.message == (
            "effective exclude list is configured, replacing the shipped default "
            "(0 modules): nothing is excluded by module name"
        )

    def test_fails_on_a_malformed_value_and_names_the_error(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(exclude_error="exclude entry 'a b' is not a dotted module name")
        finding = check_exclude(snapshot)
        assert finding.status == "fail"
        assert "exclude entry 'a b' is not a dotted module name" in finding.message
        assert finding.fix != ""

    def test_passes_without_a_computed_list(self, make_snapshot: MakeSnapshot) -> None:
        assert check_exclude(make_snapshot()).status == "pass"
