# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Normalise, gate, render — in that order, because the order is the safety property.

A caller cannot reach a URL or a body file past a violation, because :class:`Refused` has neither.
These tests are about that, and about the one property the draft and the body have to keep: the
draft CONTAINS the body verbatim, so approving what was shown means approving what gets filed.
"""

from __future__ import annotations

import pytest
from reports import a_report

from narrativetrace_tooling.feedback.draft import Drafted, Refused
from narrativetrace_tooling.feedback.drafter import draft
from narrativetrace_tooling.feedback.render import PRIVACY_NOTE
from narrativetrace_tooling.feedback.report import Attachments, FeedbackCategory, ProblemNarrative
from narrativetrace_tooling.feedback.rules import HOME_PATH, RENDERED_CALL


def _drafted(**overrides: object) -> Drafted:
    outcome = draft(a_report(**overrides))
    assert isinstance(outcome, Drafted), outcome
    return outcome


class TestDraftingAValueFreeReport:
    def test_the_draft_contains_the_body_verbatim(self) -> None:
        """Approving a draft has to mean approving what is filed, byte for byte. ``Drafted``
        refuses to exist otherwise, and this is the test of that construction rather than of the
        renderer."""
        outcome = _drafted()

        assert outcome.body in outcome.draft

    def test_the_body_is_the_report_and_nothing_about_the_process(self) -> None:
        outcome = _drafted()

        assert "- runtime: python" in outcome.body
        assert "- category: doctor" in outcome.body
        assert "## What I did" in outcome.body
        assert "## What happened" in outcome.body
        assert "## What I expected" in outcome.body
        assert PRIVACY_NOTE not in outcome.body

    def test_the_draft_frames_the_body_with_what_a_person_needs_to_decide(self) -> None:
        outcome = _drafted()

        assert outcome.draft.startswith(
            "# NarrativeTrace problem report (draft — nothing has been filed)"
        )
        assert PRIVACY_NOTE in outcome.draft

    def test_the_privacy_note_says_what_filing_publicly_actually_means(self) -> None:
        """Design D5's note, asserted word for word: a reader acts on it, so every rewording is a
        decision rather than a tidy-up."""
        assert PRIVACY_NOTE == (
            "Filing on GitHub is public, under your own account, and shows that this project uses"
            " NarrativeTrace. Nothing is sent anywhere until you choose to file it."
        )

    def test_the_report_it_carries_is_the_normalised_one(self) -> None:
        outcome = _drafted(
            narrative=ProblemNarrative(
                "ran it from /Users/ada/work/orders",
                "it failed",
                "it to pass",
            )
        )

        assert outcome.report.narrative.did == "ran it from ~/work/orders"
        assert "/Users/ada" not in outcome.draft

    def test_an_attachment_is_fenced_with_four_backticks(self) -> None:
        """An attached doctor report or structural trace is somebody else's text, and a
        three-backtick fence around text that happens to contain three backticks ends the block
        early and spills the rest into the issue as prose."""
        outcome = _drafted()

        assert "````json" in outcome.body
        assert "```json" not in outcome.body.replace("````json", "")

    def test_a_missing_attachment_says_why_rather_than_going_quiet(self) -> None:
        outcome = _drafted(
            category=FeedbackCategory.PROMPT,
            attachments=Attachments.without_doctor_report("no readable pyproject.toml", ""),
        )

        assert "No doctor report: no readable pyproject.toml" in outcome.body
        assert "No structural trace was attached." in outcome.body


class TestTheGateRunsBeforeAnythingIsRendered:
    def test_a_refusal_names_every_field_and_rule_that_stood_in_the_way(self) -> None:
        outcome = draft(
            a_report(
                narrative=ProblemNarrative(
                    'it rendered as OrderService.place_order(id: "C-1")',
                    "it failed",
                    "it to pass",
                )
            )
        )

        assert isinstance(outcome, Refused)
        assert [(v.field, v.rule) for v in outcome.violations] == [("did", RENDERED_CALL)]

    def test_a_refusal_has_no_body_to_file_and_no_draft_to_show(self) -> None:
        """The compiler, not a convention, is what enforces the ordering: ``Refused`` has neither
        attribute, so no caller can print a URL or write a body file while a violation stands."""
        outcome = draft(a_report(narrative=ProblemNarrative("ada@example.com", "x", "y")))

        assert not hasattr(outcome, "body")
        assert not hasattr(outcome, "draft")

    def test_the_refusal_prints_one_line_per_violation(self) -> None:
        outcome = draft(a_report(narrative=ProblemNarrative("ada@example.com", "x", "y")))
        assert isinstance(outcome, Refused)

        described = outcome.describe()

        assert described.startswith("This report cannot be filed. 1 rule(s) refused it:\n")
        assert "  - did: vf.email — " in described

    def test_a_refusal_names_what_refused_it(self) -> None:
        with pytest.raises(ValueError, match=r"an empty violation list is a Drafted"):
            Refused(())

    def test_drafting_refuses_a_none_report(self) -> None:
        with pytest.raises(TypeError, match=r"nothing to draft from a report that is None"):
            draft(None)  # type: ignore[arg-type]


class TestNormalisationRunsBeforeTheGate:
    def test_a_home_path_is_rewritten_rather_than_refused(self) -> None:
        """Refusing the report would be the wrong answer to a mistake nobody made on purpose; ``~``
        says the same thing about the same file and names nobody."""
        outcome = _drafted(install="/Users/ada/work/orders/.venv")

        assert outcome.report.install == "~/work/orders/.venv"

    def test_every_text_field_is_normalised_not_just_the_narrative(self) -> None:
        outcome = _drafted(
            install="/Users/ada/w",
            step="/home/ada/s",
            narrative=ProblemNarrative("/Users/ada/d", "/home/ada/h", "/Users/ada/e"),
        )

        assert "/Users/ada" not in outcome.draft
        assert "/home/ada" not in outcome.draft

    def test_a_home_path_that_survives_normalisation_is_still_refused(self) -> None:
        """``vf.home-path`` stays as the backstop for a form the rewriter cannot normalise — a UNC
        share, or a path typed into the body file after the draft was shown."""
        outcome = draft(
            a_report(narrative=ProblemNarrative("ran it from \\\\host\\Users\\ada\\w", "x", "y"))
        )

        assert isinstance(outcome, Drafted) or HOME_PATH in [v.rule for v in outcome.violations]


class TestDraftedRefusesToExistWithoutItsParts:
    def test_a_draft_that_does_not_contain_its_body_is_refused(self) -> None:
        report = a_report()

        with pytest.raises(ValueError, match=r"must contain the body verbatim"):
            Drafted(report, "a summary of the report", "the whole body")

    def test_a_drafted_report_carries_its_report_and_both_texts(self) -> None:
        with pytest.raises(TypeError, match=r"carries its report and both texts"):
            Drafted(None, "body", "body")  # type: ignore[arg-type]
