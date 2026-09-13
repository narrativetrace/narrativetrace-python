# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace.doctor.finding import failed, passed


class TestPassed:
    def test_status_is_pass(self) -> None:
        finding = passed("some.id", "it is fine", "https://example/doc")
        assert finding.status == "pass"

    def test_fix_is_empty(self) -> None:
        finding = passed("some.id", "it is fine", "https://example/doc")
        assert finding.fix == ""

    def test_carries_id_message_and_doc_url(self) -> None:
        finding = passed("some.id", "it is fine", "https://example/doc")
        assert finding.id == "some.id"
        assert finding.message == "it is fine"
        assert finding.doc_url == "https://example/doc"


class TestFailed:
    def test_status_is_fail(self) -> None:
        finding = failed("some.id", "it is broken", "fix it", "https://example/doc")
        assert finding.status == "fail"

    def test_carries_fix(self) -> None:
        finding = failed("some.id", "it is broken", "fix it", "https://example/doc")
        assert finding.fix == "fix it"
