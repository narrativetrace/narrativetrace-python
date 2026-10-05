# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import json

from narrativetrace_tooling.doctor.render import render_human, render_json
from narrativetrace_tooling.doctor.types import DoctorReport, Finding

_PASS = Finding("a.pass", "pass", "all good", "", "https://example/a", None)
_FAIL = Finding(
    "b.fail", "fail", "something is wrong", "fix it", "https://example/b", "narrativetrace-doctor"
)


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

    def test_failures_render_the_skill_under_the_fix_line(self) -> None:
        report = DoctorReport(findings=(_FAIL,), exit_code=1)
        rendered = render_human(report)
        fix_line = rendered.index("fix:  fix it")
        skill_line = rendered.index("skill: narrativetrace-doctor")
        assert fix_line < skill_line < rendered.index("docs: https://example/b")

    def test_a_finding_with_no_fixing_skill_prints_no_skill_line(self) -> None:
        no_skill_fail = Finding("c.fail", "fail", "broken", "fix it", "https://example/c", None)
        report = DoctorReport(findings=(no_skill_fail,), exit_code=1)
        rendered = render_human(report)
        assert "skill:" not in rendered

    def test_failures_render_before_passes(self) -> None:
        report = DoctorReport(findings=(_PASS, _FAIL), exit_code=1)
        rendered = render_human(report)
        assert rendered.index("b.fail") < rendered.index("a.pass")

    def test_header_names_check_and_finding_counts(self) -> None:
        report = DoctorReport(findings=(_PASS, _FAIL), exit_code=1)
        rendered = render_human(report)
        assert rendered.startswith("narrativetrace doctor — 2 check(s), 1 finding(s)")

    def test_the_whole_all_passed_rendering_word_for_word(self) -> None:
        """A full-text pin, not a handful of substring checks: this is published output a person
        or a script reads, and a substring-only assertion leaves the joiner, the blank lines and
        the exact summary sentence free to drift unnoticed."""
        report = DoctorReport(findings=(_PASS,), exit_code=0)
        assert render_human(report) == (
            "narrativetrace doctor — 1 check(s), 0 finding(s)\n"
            "\n"
            "[PASS] a.pass — all good\n"
            "\n"
            "All checks passed."
        )


class TestRenderJson:
    def test_round_trips_findings_and_exit_code(self) -> None:
        report = DoctorReport(findings=(_PASS, _FAIL), exit_code=1)
        payload = json.loads(render_json(report))
        assert payload["exit_code"] == 1
        assert len(payload["findings"]) == 2
        assert payload["findings"][0]["id"] == "a.pass"
        assert payload["findings"][1]["doc_url"] == "https://example/b"

    def test_skill_key_is_always_present_null_when_nothing_fixes_it(self) -> None:
        report = DoctorReport(findings=(_PASS, _FAIL), exit_code=1)
        payload = json.loads(render_json(report))
        assert payload["findings"][0]["skill"] is None
        assert payload["findings"][1]["skill"] == "narrativetrace-doctor"

    def test_is_pretty_printed_with_two_space_indent(self) -> None:
        report = DoctorReport(findings=(_PASS,), exit_code=0)
        assert render_json(report).startswith('{\n  "findings"')
