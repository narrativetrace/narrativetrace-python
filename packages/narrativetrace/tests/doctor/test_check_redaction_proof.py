# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakeSnapshot

from narrativetrace.doctor.checks.redaction_proof import check_redaction_proof


class TestCheckRedactionProof:
    def test_fails_with_no_test_files_at_all(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_redaction_proof(make_snapshot())
        assert finding.status == "fail"

    def test_fails_when_no_test_asserts_redacted(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(source_files={"tests/test_service.py": "assert result == 'ORD-1'"})
        assert check_redaction_proof(snapshot).status == "fail"

    def test_passes_when_a_test_prefixed_file_asserts_redacted(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            source_files={"tests/test_service.py": "assert '[REDACTED]' in rendered"}
        )
        assert check_redaction_proof(snapshot).status == "pass"

    def test_passes_when_a_suffix_style_test_file_asserts_redacted(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(source_files={"tests/service_test.py": "'[REDACTED]' in rendered"})
        assert check_redaction_proof(snapshot).status == "pass"

    def test_ignores_a_non_test_file_asserting_the_marker(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(source_files={"service.py": "REDACTED_MARKER = '[REDACTED]'"})
        assert check_redaction_proof(snapshot).status == "fail"

    def test_does_not_match_a_sibling_module_sharing_a_prefix(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """`test_x.py` is recognized; a module merely named like one (`testable.py`) is not."""
        snapshot = make_snapshot(source_files={"testable.py": "'[REDACTED]' in rendered"})
        assert check_redaction_proof(snapshot).status == "fail"
