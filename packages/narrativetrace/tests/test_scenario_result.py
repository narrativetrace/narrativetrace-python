# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The two spellings of a scenario result, and the guard that keeps them from drifting.

`chapter-tree.schema.json` constrains `scenario.result` to `success`/`error`; the Markdown caption
reads `PASSED`/`FAILED`. Free-form strings put the display spelling into the JSON artifact, which
the schema rejects — so an out-of-contract value must be unrepresentable, not merely untested.
"""

from __future__ import annotations

import pytest

from narrativetrace import ScenarioResult, TraceMetadata


class TestSpellings:
    def test_success_carries_both_spellings(self) -> None:
        assert ScenarioResult.SUCCESS.wire_name == "success"
        assert ScenarioResult.SUCCESS.display_name == "PASSED"

    def test_error_carries_both_spellings(self) -> None:
        assert ScenarioResult.ERROR.wire_name == "error"
        assert ScenarioResult.ERROR.display_name == "FAILED"

    def test_every_wire_spelling_is_one_the_canonical_schema_allows(self) -> None:
        assert {result.wire_name for result in ScenarioResult} == {"success", "error"}


class TestOfOutcomeFlag:
    def test_a_failed_test_is_an_error(self) -> None:
        assert ScenarioResult.of(failed=True) is ScenarioResult.ERROR

    def test_a_passing_test_is_a_success(self) -> None:
        assert ScenarioResult.of(failed=False) is ScenarioResult.SUCCESS


class TestFromText:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("success", ScenarioResult.SUCCESS),
            ("PASSED", ScenarioResult.SUCCESS),
            ("passed", ScenarioResult.SUCCESS),
            ("  Success  ", ScenarioResult.SUCCESS),
            ("error", ScenarioResult.ERROR),
            ("FAILED", ScenarioResult.ERROR),
            ("Failed", ScenarioResult.ERROR),
        ],
    )
    def test_parses_either_spelling_case_insensitively(
        self, text: str, expected: ScenarioResult
    ) -> None:
        assert ScenarioResult.from_text(text) is expected

    @pytest.mark.parametrize("text", ["ok", "fail", "SUCCESS_", "", "  ", "partial"])
    def test_rejects_anything_the_schema_would_refuse(self, text: str) -> None:
        with pytest.raises(ValueError, match=r"\Aunknown scenario result "):
            ScenarioResult.from_text(text)

    def test_rejects_a_non_string(self) -> None:
        with pytest.raises(TypeError, match=r"\Ascenario result must be a string\Z"):
            ScenarioResult.from_text(None)  # type: ignore[arg-type]


class TestTraceMetadata:
    def test_carries_a_scenario_result(self) -> None:
        assert TraceMetadata("s", ScenarioResult.ERROR).result is ScenarioResult.ERROR

    @pytest.mark.parametrize("text", ["success", "PASSED"])
    def test_a_string_is_parsed_for_compatibility(self, text: str) -> None:
        assert TraceMetadata("s", text).result is ScenarioResult.SUCCESS  # type: ignore[arg-type]

    def test_an_out_of_contract_string_fails_here_not_in_the_artifact(self) -> None:
        with pytest.raises(ValueError, match=r"\Aunknown scenario result 'ok'"):
            TraceMetadata("s", "ok")  # type: ignore[arg-type]

    def test_a_value_that_is_neither_a_result_nor_text_is_rejected(self) -> None:
        with pytest.raises(TypeError, match=r"\Aresult must be a ScenarioResult\Z"):
            TraceMetadata("s", 1)  # type: ignore[arg-type]
