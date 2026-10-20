# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakeSnapshot

from narrativetrace_tooling.doctor.checks.service_identity import check_service_identity

_UNNAMED_CONTEXT = "context = ContextVarNarrativeContext()\n"


class TestCheckServiceIdentity:
    def test_passes_when_no_source_builds_a_context(self, make_snapshot: MakeSnapshot) -> None:
        assert check_service_identity(make_snapshot()).status == "pass"

    def test_fails_when_non_test_source_builds_a_context_with_no_service_name(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(source_files={"app/main.py": _UNNAMED_CONTEXT})
        finding = check_service_identity(snapshot)
        assert finding.status == "fail"
        assert "app/main.py" in finding.message
        assert "unknown_service:python" in finding.message

    def test_the_fix_names_the_environment_key_and_the_constructor_argument(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(source_files={"app/main.py": _UNNAMED_CONTEXT})
        fix = check_service_identity(snapshot).fix
        assert "NARRATIVETRACE_SERVICE_NAME" in fix
        assert 'service_identity=ServiceIdentity("orders")' in fix

    def test_passes_when_the_environment_names_the_service(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            env={"NARRATIVETRACE_SERVICE_NAME": "orders"},
            source_files={"app/main.py": _UNNAMED_CONTEXT},
        )
        assert check_service_identity(snapshot).status == "pass"

    def test_a_blank_environment_name_does_not_name_the_service(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            env={"NARRATIVETRACE_SERVICE_NAME": "  "},
            source_files={"app/main.py": _UNNAMED_CONTEXT},
        )
        assert check_service_identity(snapshot).status == "fail"

    def test_passes_when_the_source_passes_a_service_identity(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        content = (
            "context = ContextVarNarrativeContext(\n"
            '    service_identity=ServiceIdentity("orders"))\n'
        )
        snapshot = make_snapshot(source_files={"app/main.py": content})
        assert check_service_identity(snapshot).status == "pass"

    def test_a_service_identity_in_another_file_names_the_service(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            source_files={
                "app/main.py": _UNNAMED_CONTEXT,
                "app/identity.py": 'IDENTITY = ServiceIdentity("orders")\n',
            }
        )
        assert check_service_identity(snapshot).status == "pass"

    def test_test_source_alone_is_not_flagged(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            source_files={
                "tests/test_orders.py": _UNNAMED_CONTEXT,
                "test_top.py": _UNNAMED_CONTEXT,
                "conftest.py": _UNNAMED_CONTEXT,
                "pkg/tests/helpers.py": _UNNAMED_CONTEXT,
            }
        )
        assert check_service_identity(snapshot).status == "pass"

    def test_a_directory_that_only_resembles_tests_is_not_exempt(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(source_files={"latests/main.py": _UNNAMED_CONTEXT})
        assert check_service_identity(snapshot).status == "fail"

    def test_a_non_python_file_is_not_source(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(source_files={"README.md": _UNNAMED_CONTEXT})
        assert check_service_identity(snapshot).status == "pass"
