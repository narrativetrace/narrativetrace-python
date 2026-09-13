# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakeSnapshot

from narrativetrace.doctor.checks.not_traced_unused import check_not_traced_unused


class TestCheckNotTracedUnused:
    def test_passes_with_no_source_files(self, make_snapshot: MakeSnapshot) -> None:
        assert check_not_traced_unused(make_snapshot()).status == "pass"

    def test_passes_when_not_traced_field_is_actually_called(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        content = (
            "from narrativetrace import not_traced_field\n"
            "@dataclass\nclass C:\n    token: str = not_traced_field()\n"
        )
        snapshot = make_snapshot(source_files={"models.py": content})
        assert check_not_traced_unused(snapshot).status == "pass"

    def test_fails_when_not_traced_field_is_imported_but_never_called(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        content = "from narrativetrace import not_traced_field\n\nclass C:\n    pass\n"
        snapshot = make_snapshot(source_files={"models.py": content})
        finding = check_not_traced_unused(snapshot)
        assert finding.status == "fail"
        assert "models.py" in finding.message
        assert "not_traced_field" in finding.message

    def test_passes_when_nt_not_traced_attr_lists_real_fields(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        content = "class C:\n    __nt_not_traced__ = ('token',)\n"
        snapshot = make_snapshot(source_files={"models.py": content})
        assert check_not_traced_unused(snapshot).status == "pass"

    def test_fails_when_nt_not_traced_attr_is_empty(self, make_snapshot: MakeSnapshot) -> None:
        content = "class C:\n    __nt_not_traced__ = ()\n"
        snapshot = make_snapshot(source_files={"models.py": content})
        finding = check_not_traced_unused(snapshot)
        assert finding.status == "fail"
        assert "lists no fields" in finding.message

    def test_fails_when_nt_not_traced_attr_is_an_empty_list(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        content = "class C:\n    __nt_not_traced__ = []\n"
        snapshot = make_snapshot(source_files={"models.py": content})
        assert check_not_traced_unused(snapshot).status == "fail"

    def test_ignores_non_python_files(self, make_snapshot: MakeSnapshot) -> None:
        content = "from narrativetrace import not_traced_field\n"
        snapshot = make_snapshot(source_files={"README.md": content})
        assert check_not_traced_unused(snapshot).status == "pass"
