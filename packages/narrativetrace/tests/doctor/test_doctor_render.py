# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import json

from narrativetrace.doctor.render import render_human, render_json
from narrativetrace.doctor.types import DoctorReport, Finding

_PASS = Finding("a.pass", "pass", "all good", "", "https://example/a")
_FAIL = Finding("b.fail", "fail", "something is wrong", "fix it", "https://example/b")


class TestRenderHuman:
    def test_all_passed_summary(self) -> None:
        report = DoctorReport(findings=(_PASS,), exit_code=0)
        rendered = render_human(report)
        assert "All checks passed." in rendered
        assert "[PASS] a.pass — all good" in rendered

    def test_failures_render_fix_and_docs(self) -> None:
        report = DoctorReport(findings=(_FAIL,), exit_code=1)
        rendered = render_human(report)
        assert "[FAIL] b.fail — something is wrong" in rendered
        assert "fix:  fix it" in rendered
        assert "docs: https://example/b" in rendered
        assert "1 finding(s). Exit code 1." in rendered

    def test_failures_render_before_passes(self) -> None:
        report = DoctorReport(findings=(_PASS, _FAIL), exit_code=1)
        rendered = render_human(report)
        assert rendered.index("b.fail") < rendered.index("a.pass")

    def test_header_names_check_and_finding_counts(self) -> None:
        report = DoctorReport(findings=(_PASS, _FAIL), exit_code=1)
        rendered = render_human(report)
        assert rendered.startswith("narrativetrace doctor — 2 check(s), 1 finding(s)")


class TestRenderJson:
    def test_round_trips_findings_and_exit_code(self) -> None:
        report = DoctorReport(findings=(_PASS, _FAIL), exit_code=1)
        payload = json.loads(render_json(report))
        assert payload["exit_code"] == 1
        assert len(payload["findings"]) == 2
        assert payload["findings"][0]["id"] == "a.pass"
        assert payload["findings"][1]["doc_url"] == "https://example/b"

    def test_is_pretty_printed(self) -> None:
        report = DoctorReport(findings=(_PASS,), exit_code=0)
        assert "\n" in render_json(report)
