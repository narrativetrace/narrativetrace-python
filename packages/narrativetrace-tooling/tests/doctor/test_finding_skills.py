# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The whole table, spelled out. A change of mind about which skill fixes which finding class is a
change to a published contract — an agent reads ``skill`` and follows that procedure — so it should
have to edit a row here, not just a line of production code."""

from __future__ import annotations

import pytest

from narrativetrace_tooling.doctor.finding_skills import for_check, knows

_ADD = "add-narrative-tracing"
_DOCTOR = "narrativetrace-doctor"


class TestForCheck:
    @pytest.mark.parametrize(
        ("check_id", "skill"),
        [
            ("toolchain.pytest-version", _ADD),
            ("toolchain.package-versions", _ADD),
            ("config.pytest-plugin-registered", _ADD),
            ("config.output-env", _DOCTOR),
            ("config.unknown-keys", _DOCTOR),
            ("trap.parameter-names", _ADD),
            ("trap.silent-sink", _DOCTOR),
            ("trap.redaction-proof", _DOCTOR),
            ("trap.approval-traces", _DOCTOR),
            ("trap.llms-before-you-start", _ADD),
        ],
    )
    def test_names_the_skill_that_fixes_each_finding_class(self, check_id: str, skill: str) -> None:
        assert for_check(check_id) == skill

    @pytest.mark.parametrize("check_id", ["toolchain.python-version", "config.skills-installed"])
    def test_names_no_skill_where_none_fixes_it(self, check_id: str) -> None:
        """Two ids carry no skill on purpose, and the table still KNOWS them — decided, not
        forgotten."""
        assert for_check(check_id) is None
        assert knows(check_id) is True

    def test_an_id_the_table_never_heard_of_is_neither_known_nor_mapped(self) -> None:
        assert for_check("trap.invented-yesterday") is None
        assert knows("trap.invented-yesterday") is False
