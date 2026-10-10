# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The two texts a cleared report becomes: the body that gets filed, and the draft a person reads
before deciding to file it.

Ports Java ``FeedbackRender``. INTENT: one renderer, so the draft cannot say something the body does
not. The draft CONTAINS the body verbatim — :class:`~narrativetrace_tooling.feedback.draft.Drafted`
refuses to exist otherwise — because approving a draft has to mean approving what is filed, byte for
byte, and a summary is not that.

**@llmNote** Fences are four backticks, not three. An attached doctor report or structural trace is
somebody else's text, and a three-backtick fence around text that happens to contain three backticks
ends the block early and spills the rest into the issue as prose.
"""

from __future__ import annotations

from typing import Final

from narrativetrace_tooling.feedback.report import Attachments, FeedbackReport, ProblemNarrative

PRIVACY_NOTE: Final = (
    "Filing on GitHub is public, under your own account, and shows that this project uses"
    " NarrativeTrace. Nothing is sent anywhere until you choose to file it."
)
"""What filing publicly actually means (design D5). A reader acts on this, so it is asserted word
for word by a test — every rewording is a decision, not a tidy-up."""

DRAFT_HEADING: Final = "# NarrativeTrace problem report (draft — nothing has been filed)"

_FENCE: Final = "````"


def body(report: FeedbackReport) -> str:
    """The report in Markdown: what gets filed, with nothing in it about the process."""
    return _facts(report) + _narrative(report.narrative) + _attachments(report.attachments)


def draft_text(body_markdown: str) -> str:
    """The body, framed by what a person needs in order to decide: the privacy note.

    Takes the rendered body rather than the report, so there is exactly one place the body is
    rendered and the containment property cannot be an accident of two renderers agreeing.
    """
    return f"{DRAFT_HEADING}\n\n{body_markdown}\n---\n\n{PRIVACY_NOTE}\n"


def _facts(report: FeedbackReport) -> str:
    agent = report.agent.describe() or "not reported"
    return (
        f"- runtime: {report.runtime}\n"
        f"- category: {report.category.id}\n"
        f"- install: {report.install}\n"
        f"- step: {report.step}\n"
        f"- language: {report.language}\n"
        f"- agent: {agent}\n\n"
    )


def _narrative(narrative: ProblemNarrative) -> str:
    return (
        f"## What I did\n\n{narrative.did}\n\n"
        f"## What happened\n\n{narrative.happened}\n\n"
        f"## What I expected\n\n{narrative.expected}\n\n"
    )


def _attachments(attachments: Attachments) -> str:
    doctor = (
        _fenced(attachments.doctor_report, "json")
        if attachments.has_doctor_report
        else f"No doctor report: {attachments.doctor_unavailable}\n\n"
    )
    trace = (
        _fenced(attachments.structural_trace, "")
        if attachments.has_structural_trace
        else "No structural trace was attached.\n"
    )
    return f"## Doctor report\n\n{doctor}## Structural trace\n\n{trace}"


def _fenced(content: str, language: str) -> str:
    return f"{_FENCE}{language}\n{content.strip()}\n{_FENCE}\n\n"
