# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The gate over a whole report's named fields: which field broke which rule, in what order, and
the ONE field-scoped exemption.

The exemption is the defect Java's milestone 2 found by running the real verb against a real
project, after 654 green tests had missed it (cross-port item 1). Its tests are the reason this
module exists separately from ``test_value_free_rules.py``: the rules are about TEXT, and this is
about which rules read which FIELD.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from reports import STRUCTURAL_TRACE, doctor_report_json, doctor_snapshot

from narrativetrace_tooling.doctor.doctor import run_doctor
from narrativetrace_tooling.doctor.render import render_json
from narrativetrace_tooling.feedback.check import (
    DOCTOR_REPORT_FIELD,
    ValueFreeViolation,
    rules_refusing,
    violations,
)
from narrativetrace_tooling.feedback.matchers import REDACTION_MARKER
from narrativetrace_tooling.feedback.rules import (
    ALL_RULES,
    EMAIL,
    HOME_PATH,
    MARKER,
    RENDERED_CALL,
    VALUE_SHAPE,
)

_FASTAPI_PROJECT = '[project]\nname = "orders"\ndependencies = ["fastapi", "narrativetrace"]\n'
_PERSON_WRITTEN_FIELDS = ("install", "step", "did", "happened", "expected", "agent", "trace")


class TestViolations:
    def test_names_the_field_and_the_rule_that_refused_it(self) -> None:
        found = violations({"happened": 'it rendered as OrderService.place_order(id: "C-1")'})

        assert found == (ValueFreeViolation("happened", RENDERED_CALL),)

    def test_a_value_free_report_has_no_violation_at_all(self) -> None:
        found = violations(
            {
                "step": "trap.redaction-proof",
                "install": "narrativetrace==0.2.0",
                "did": "ran the doctor, applied the fix it printed, ran it again",
                "happened": "the same check still failed, with the same message",
                "expected": "the check to pass once the test asserts the marker",
                DOCTOR_REPORT_FIELD: doctor_report_json(),
                "trace": STRUCTURAL_TRACE,
            }
        )

        assert found == ()

    def test_reports_every_rule_a_field_breaks_in_rule_order(self) -> None:
        """Every rule is reported, not the first: a report that leaks two different shapes should
        be fixed once, not twice."""
        found = violations({"happened": "ada@example.com in /Users/ada/work/"})

        assert [violation.rule for violation in found] == [EMAIL, HOME_PATH]

    def test_walks_the_fields_in_the_order_they_were_given(self) -> None:
        """So the same report always refuses in the same words, which is what lets a test assert
        on them."""
        found = violations(
            {"expected": "/Users/ada/work/", "did": "ada@example.com"},
        )

        assert [violation.field for violation in found] == ["expected", "did"]

    def test_refuses_a_none_field_map_and_a_none_field_value(self) -> None:
        """The drafter represents an absent field as ``""``, so a ``None`` here is a caller's bug
        and must not be read as empty — a field read as empty is a field no rule looked at."""
        with pytest.raises(TypeError, match=r"never None"):
            violations(None)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match=r'field "did" is None'):
            violations({"did": None})  # type: ignore[dict-item]

    def test_an_empty_report_is_filable_rather_than_an_error(self) -> None:
        assert violations({}) == ()


class TestTheDoctorReportFieldExemption:
    def test_the_doctors_own_report_may_quote_the_redaction_marker(self) -> None:
        """The doctor's check vocabulary NAMES the marker: ``trap.redaction-proof`` IS the check
        "a test asserts the literal [REDACTED]", and its message says so whether it passes or
        fails. So ``vf.marker`` read against that one generated field refused every report from
        every project that has NarrativeTrace installed at all — the verb could draft nothing."""
        found = violations({DOCTOR_REPORT_FIELD: doctor_report_json()})

        assert found == ()

    @pytest.mark.parametrize("field", _PERSON_WRITTEN_FIELDS)
    def test_the_marker_is_still_refused_in_every_field_a_person_wrote(self, field: str) -> None:
        """The exemption is ONE field and ONE rule. Everywhere else the marker still proves that
        the text came from a rendered artifact."""
        found = violations({field: f"it rendered as password: {REDACTION_MARKER}"})

        assert MARKER in [violation.rule for violation in found], field

    def test_every_other_rule_still_reads_the_doctors_report(self) -> None:
        """Which is the whole point of exempting one rule rather than the field: the doctor's
        messages name project files and classes, so an email, a home path or a credential shape
        inside one still refuses the whole draft."""
        planted = (
            '{"findings": [{"message": "ada@example.com under /Users/ada/work/ with'
            ' ghp_abcd1234efgh"}]}'
        )

        found = violations({DOCTOR_REPORT_FIELD: planted})

        assert {violation.rule for violation in found} >= {EMAIL, HOME_PATH, VALUE_SHAPE}

    def test_exactly_one_rule_is_exempt_and_only_for_that_one_field(self) -> None:
        """Stated as a difference rather than as a list, so adding an eleventh rule cannot
        silently widen the exemption."""
        marker_text = f"nothing but the marker: {REDACTION_MARKER}"

        exempt_field = {violation.rule for violation in violations({DOCTOR_REPORT_FIELD: ""})}
        read_by_doctor_field = set(ALL_RULES) - {MARKER}

        assert exempt_field == set()
        assert violations({DOCTOR_REPORT_FIELD: marker_text}) == ()
        assert MARKER not in read_by_doctor_field
        assert len(read_by_doctor_field) == len(ALL_RULES) - 1

    def test_the_exempt_field_is_named_by_a_string_a_near_miss_does_not_match(self) -> None:
        """A renamed field would silently re-arm the rule and the verb would stop drafting
        anything again. ``doctor report`` is exempt; ``doctor reports`` is not."""
        assert violations({DOCTOR_REPORT_FIELD: REDACTION_MARKER}) == ()
        assert violations({DOCTOR_REPORT_FIELD + "s": REDACTION_MARKER}) != ()

    def test_the_text_scoped_reading_of_the_rules_still_refuses_the_marker(self) -> None:
        """``rules_refusing`` has no field to exempt, and it is what the shared corpus replay
        uses — so a corpus row's verdict never depends on which field a value arrived in."""
        assert MARKER in rules_refusing(REDACTION_MARKER)


class TestTheDoctorReportIsTheRealGeneratedArtifact:
    def test_the_generated_report_really_does_quote_the_redaction_marker(self) -> None:
        """The premise of the exemption, asserted rather than assumed. If the doctor's own wording
        ever stops naming the marker, this fails and the exemption becomes dead configuration that
        reads as protection."""
        assert REDACTION_MARKER in doctor_report_json()

    def test_the_generated_report_is_the_doctors_own_json_shape(self) -> None:
        report = doctor_report_json()

        assert '"findings"' in report
        assert '"trap.redaction-proof"' in report
        assert '"exit_code"' in report

    def test_without_the_exemption_that_report_would_be_refused(self) -> None:
        """The defect itself, as a test: the text-scoped reading of the same bytes IS refused, and
        only the field-scoped reading lets it through. A port that skipped the exemption would see
        this pass and the one above fail."""
        assert MARKER in rules_refusing(doctor_report_json())


class TestTheDoctorReportIsReadAsTheTextItCarries:
    """The doctor's report is JSON, and JSON escapes a newline as the two characters ``\\n``.
    Read raw, a framework fix line that starts with a Python decorator (``\\n@app.get(``) reads
    as ``n@app.get`` — an email address to :data:`EMAIL` — so every report from a FastAPI project
    was refused. The field is read as the strings the JSON carries, which no rule is weaker on."""

    def test_a_decorator_starting_a_fix_line_is_not_an_email(self) -> None:
        report = json.dumps({"findings": [{"fix": 'app = FastAPI()\n\n\n@app.get("/x")'}]})
        assert EMAIL in rules_refusing(report)

        assert violations({DOCTOR_REPORT_FIELD: report}) == ()

    def test_a_fastapi_projects_real_doctor_report_is_not_refused(self) -> None:
        snapshot = replace(doctor_snapshot(), source_files={"pyproject.toml": _FASTAPI_PROJECT})
        report = render_json(run_doctor(snapshot))
        assert "@app.get(" in report

        assert violations({DOCTOR_REPORT_FIELD: report}) == ()

    def test_the_raw_bytes_of_that_report_are_what_the_email_rule_misread(self) -> None:
        snapshot = replace(doctor_snapshot(), source_files={"pyproject.toml": _FASTAPI_PROJECT})
        assert EMAIL in rules_refusing(render_json(run_doctor(snapshot)))

    def test_an_email_inside_a_doctor_message_is_still_refused(self) -> None:
        report = json.dumps({"findings": [{"message": "ask ada@example.com\n@app.get"}]})

        assert [v.rule for v in violations({DOCTOR_REPORT_FIELD: report})] == [EMAIL]

    def test_an_email_glued_to_an_escaped_newline_is_still_refused(self) -> None:
        report = json.dumps({"findings": [{"fix": "line\nada@example.com"}]})

        assert [v.rule for v in violations({DOCTOR_REPORT_FIELD: report})] == [EMAIL]

    def test_a_doctor_report_that_is_not_json_is_read_as_it_is(self) -> None:
        assert [v.rule for v in violations({DOCTOR_REPORT_FIELD: "x n@app.get( y"})] == [EMAIL]

    @pytest.mark.parametrize("depth", [500, 100_000])
    def test_a_deeply_nested_report_is_read_without_exhausting_the_stack(self, depth: int) -> None:
        report = "[" * depth + '"ada@example.com"' + "]" * depth

        assert [v.rule for v in violations({DOCTOR_REPORT_FIELD: report})] == [EMAIL]

    def test_numbers_booleans_and_nulls_are_not_text_the_report_carries(self) -> None:
        report = json.dumps({"findings": [None, 2.5, True, 1999]})

        assert violations({DOCTOR_REPORT_FIELD: report}) == ()


class TestViolationDescribes:
    def test_a_violation_prints_the_field_the_rule_id_and_what_to_do(self) -> None:
        line = ValueFreeViolation("happened", RENDERED_CALL).describe()

        assert line.startswith("happened: vf.rendered-call — ")
        assert RENDERED_CALL.reason in line

    def test_a_violation_names_the_field_it_was_found_in(self) -> None:
        with pytest.raises(ValueError, match=r"names the field"):
            ValueFreeViolation("", RENDERED_CALL)

    def test_a_violation_names_the_rule_that_refused_it(self) -> None:
        with pytest.raises(TypeError, match=r"names the rule"):
            ValueFreeViolation("happened", None)  # type: ignore[arg-type]
