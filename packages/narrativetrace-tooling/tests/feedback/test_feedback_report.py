# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The report every channel reads: the closed category set, the three mandatory sentences, the
exclusive attachment pair, and which fields the gate inspects.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from reports import STRUCTURAL_TRACE, a_report, doctor_report_json

from narrativetrace_tooling.feedback import report as report_module
from narrativetrace_tooling.feedback.check import DOCTOR_REPORT_FIELD
from narrativetrace_tooling.feedback.report import (
    AgentIdentity,
    Attachments,
    FeedbackCategory,
    FeedbackReport,
    ProblemNarrative,
)


@pytest.fixture
def complete() -> Iterator[FeedbackReport]:
    built = a_report()
    assert report_module._invariant(built), "the report is inconsistent before the test"
    yield built
    assert report_module._invariant(built), "the test left the report inconsistent"


class TestFeedbackCategory:
    def test_the_four_categories_are_the_ones_the_issue_form_offers(self) -> None:
        assert [category.id for category in FeedbackCategory] == [
            "prompt",
            "skill",
            "doctor",
            "library",
        ]

    @pytest.mark.parametrize(
        ("category", "required"),
        [
            (FeedbackCategory.PROMPT, False),
            (FeedbackCategory.SKILL, True),
            (FeedbackCategory.DOCTOR, True),
            (FeedbackCategory.LIBRARY, False),
        ],
    )
    def test_only_a_doctor_or_skill_report_is_meaningless_without_the_doctors_json(
        self, category: FeedbackCategory, required: bool
    ) -> None:
        """Q3 as ruled: a complaint about the doctor or a skill is unarguable only with the
        doctor's own JSON beside it, while a complaint about the published prompt or the library
        may be filed from a project whose build cannot run the doctor at all."""
        assert category.requires_doctor_report is required

    def test_a_category_is_found_by_its_id(self) -> None:
        assert FeedbackCategory.of_id("doctor") is FeedbackCategory.DOCTOR

    def test_an_unknown_id_is_refused_rather_than_defaulted(self) -> None:
        """A silent fallback would file a report into the wrong triage queue."""
        with pytest.raises(ValueError, match=r'unknown category "doctr"'):
            FeedbackCategory.of_id("doctr")


class TestProblemNarrative:
    def test_keeps_the_three_sentences(self) -> None:
        narrative = ProblemNarrative("ran it", "it failed", "it to pass")

        assert (narrative.did, narrative.happened, narrative.expected) == (
            "ran it",
            "it failed",
            "it to pass",
        )

    @pytest.mark.parametrize("missing", ["did", "happened", "expected"])
    def test_a_sentence_is_text_never_none(self, missing: str) -> None:
        """``None`` and ``""`` are different mistakes: one is a caller who passed nothing, the
        other a reporter who typed nothing, and only the second has a message worth printing."""
        sentences: dict[str, str | None] = {
            "did": "ran it",
            "happened": "it failed",
            "expected": "it to pass",
        }
        sentences[missing] = None

        with pytest.raises(TypeError, match=rf'"{missing}" is text, never None'):
            ProblemNarrative(**sentences)  # type: ignore[arg-type]

    @pytest.mark.parametrize("missing", ["did", "happened", "expected"])
    def test_every_sentence_is_mandatory(self, missing: str) -> None:
        """ "It does not work" is not a report. The difference between what happened and what was
        expected is what makes one triageable without a conversation — and a conversation is
        exactly what nobody gets when the reporter is an agent whose session has ended."""
        sentences = {"did": "ran it", "happened": "it failed", "expected": "it to pass"}
        sentences[missing] = "   "

        with pytest.raises(ValueError, match=rf'"{missing}" must say something'):
            ProblemNarrative(**sentences)


class TestAgentIdentity:
    def test_an_agent_that_did_not_name_itself_describes_as_nothing(self) -> None:
        assert AgentIdentity.unknown().describe() == ""

    def test_a_product_alone_is_the_whole_line(self) -> None:
        assert AgentIdentity("example-cli", "").describe() == "example-cli"

    def test_a_product_and_model_are_joined(self) -> None:
        assert AgentIdentity("example-cli", "example-model").describe() == (
            "example-cli / example-model"
        )

    def test_an_unknown_field_is_the_empty_string_never_none(self) -> None:
        """Neither field is verified and neither is required — an agent that will not name itself
        still gets to file — so "unknown" has one spelling and it is not ``None``."""
        with pytest.raises(TypeError, match=r"never None"):
            AgentIdentity(None, "")  # type: ignore[arg-type]


class TestAttachments:
    def test_the_doctors_json_and_one_structural_trace(self) -> None:
        attachments = Attachments.of(doctor_report_json(), STRUCTURAL_TRACE)

        assert attachments.has_doctor_report
        assert attachments.has_structural_trace
        assert attachments.doctor_unavailable == ""

    def test_a_project_whose_doctor_cannot_run_says_why(self) -> None:
        attachments = Attachments.without_doctor_report("no readable pyproject.toml", "")

        assert not attachments.has_doctor_report
        assert attachments.doctor_unavailable == "no readable pyproject.toml"

    def test_the_doctor_report_and_its_absence_are_exclusive_and_exhaustive(self) -> None:
        """ "No doctor report and no reason" would read, to triage, as a reporter who did not
        bother rather than as a project whose build cannot run the task — and those two get
        different answers."""
        with pytest.raises(ValueError, match=r"never both and never neither"):
            Attachments("", "", "")
        with pytest.raises(ValueError, match=r"never both and never neither"):
            Attachments("{}", "no pyproject", "")

    def test_an_absent_attachment_is_the_empty_string_never_none(self) -> None:
        with pytest.raises(TypeError, match=r"never None"):
            Attachments(None, "no pyproject", "")  # type: ignore[arg-type]


class TestFeedbackReport:
    def test_keeps_everything_it_was_given(self, complete: FeedbackReport) -> None:
        assert complete.runtime == "python"
        assert complete.category is FeedbackCategory.DOCTOR
        assert complete.step == "trap.redaction-proof"
        assert complete.language == "en"
        assert report_module._invariant(complete) is True

    @pytest.mark.parametrize("field", ["runtime", "install", "step", "language"])
    def test_every_mandatory_text_field_must_say_something(self, field: str) -> None:
        with pytest.raises(ValueError, match=rf'"{field}" must not be blank'):
            a_report(**{field: "  "})

    @pytest.mark.parametrize("field", ["runtime", "install", "step", "language"])
    def test_every_mandatory_text_field_is_text_never_none(self, field: str) -> None:
        with pytest.raises(TypeError, match=rf'"{field}" is text, never None'):
            a_report(**{field: None})

    def test_a_doctor_report_needs_the_doctors_json(self) -> None:
        with pytest.raises(ValueError, match=r"needs the doctor's JSON report"):
            a_report(
                category=FeedbackCategory.DOCTOR,
                attachments=Attachments.without_doctor_report("no pyproject", ""),
            )

    def test_a_prompt_report_may_be_filed_without_it(self) -> None:
        built = a_report(
            category=FeedbackCategory.PROMPT,
            attachments=Attachments.without_doctor_report("no readable pyproject.toml", ""),
        )

        assert report_module._invariant(built)
        assert built.fields()[DOCTOR_REPORT_FIELD] == ""

    def test_the_runtime_must_be_canonical_because_it_becomes_a_label(self) -> None:
        with pytest.raises(ValueError, match=r"becomes a runtime: label"):
            a_report(runtime="Python 3.12")

    def test_the_parts_are_mandatory_rather_than_defaulted(self) -> None:
        with pytest.raises(TypeError, match=r"needs a category, a narrative"):
            a_report(narrative=None)


class TestTheFieldsTheGateInspects:
    def test_every_field_that_reaches_a_url_or_a_body_file_is_inspected(
        self, complete: FeedbackReport
    ) -> None:
        """Deliberately EVERY field, the install coordinate and the agent line included: those two
        look harmless and are the two a wrapper script is most likely to interpolate into."""
        assert list(complete.fields()) == [
            "install",
            "step",
            "did",
            "happened",
            "expected",
            "agent",
            DOCTOR_REPORT_FIELD,
            "trace",
        ]

    def test_the_exempt_field_is_one_the_report_actually_carries(
        self, complete: FeedbackReport
    ) -> None:
        """The gate names the exempt field by a string, so this report and that constant have to
        agree: a renamed field here silently re-arms ``vf.marker`` on the doctor's own JSON and
        the verb stops drafting anything at all."""
        assert DOCTOR_REPORT_FIELD in complete.fields()

    def test_no_field_is_ever_none_so_the_gate_never_reads_one_as_empty(self) -> None:
        built = a_report(
            category=FeedbackCategory.PROMPT,
            agent=AgentIdentity.unknown(),
            attachments=Attachments.without_doctor_report("no readable pyproject.toml", ""),
        )

        assert all(text is not None for text in built.fields().values())
        assert built.fields()["agent"] == ""
        assert built.fields()["trace"] == ""

    def test_a_single_field_override_keeps_everything_else(self, complete: FeedbackReport) -> None:
        moved = complete.with_fields(step="trap.llms-before-you-start")

        assert moved.step == "trap.llms-before-you-start"
        assert moved.install == complete.install
        assert moved.narrative == complete.narrative
        assert report_module._invariant(moved)
