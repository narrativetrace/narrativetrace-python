# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import pytest

from narrativetrace_tooling.doctor.finding import failed, passed
from narrativetrace_tooling.doctor.types import Finding


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

    def test_skill_is_derived_from_the_table(self) -> None:
        finding = passed("config.output-env", "it is fine", "https://example/doc")
        assert finding.skill == "narrativetrace-doctor"

    def test_skill_is_none_for_an_id_the_table_never_heard_of(self) -> None:
        finding = passed("some.id", "it is fine", "https://example/doc")
        assert finding.skill is None


class TestFailed:
    def test_status_is_fail(self) -> None:
        finding = failed("some.id", "it is broken", "fix it", "https://example/doc")
        assert finding.status == "fail"

    def test_carries_fix(self) -> None:
        finding = failed("some.id", "it is broken", "fix it", "https://example/doc")
        assert finding.fix == "fix it"

    def test_skill_is_derived_from_the_table(self) -> None:
        finding = failed(
            "trap.llms-before-you-start", "it is broken", "fix it", "https://example/doc"
        )
        assert finding.skill == "add-narrative-tracing"


class TestFindingSkillGuard:
    def test_a_blank_skill_is_rejected(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"\Aa finding names the skill that fixes it, or None — never a blank name\Z",
        ):
            Finding("some.id", "pass", "it is fine", "", "https://example/doc", "   ")

    def test_none_is_accepted(self) -> None:
        finding = Finding("some.id", "pass", "it is fine", "", "https://example/doc", None)
        assert finding.skill is None
