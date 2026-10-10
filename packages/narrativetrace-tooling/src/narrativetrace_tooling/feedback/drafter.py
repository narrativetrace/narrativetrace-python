# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Turns a gathered report into something that may be shown to a person — or into a refusal that
names what is in the way.

Ports Java ``FeedbackDrafter``. INTENT: three things in one place, in this order, because the order
is the safety property. Normalise what can be normalised (a home path becomes ``~``); run every
value-free rule over every field that would be filed; render the two texts ONLY if nothing refused.
A caller cannot reach a URL or a body file past a violation, because
:class:`~narrativetrace_tooling.feedback.draft.Refused` has neither.

**@sideEffects** None. This returns text; writing it to disk is the entry point's job, and that
separation is what lets every test here be hermetic.
"""

from __future__ import annotations

from narrativetrace_tooling.feedback import render
from narrativetrace_tooling.feedback.check import violations
from narrativetrace_tooling.feedback.draft import Drafted, FeedbackDraft, Refused
from narrativetrace_tooling.feedback.home_paths import to_tilde
from narrativetrace_tooling.feedback.report import Attachments, FeedbackReport, ProblemNarrative


def draft(report: FeedbackReport) -> FeedbackDraft:
    """Normalise, gate, and render.

    :raises TypeError: when ``report`` is ``None``
    """
    if report is None:
        raise TypeError("there is nothing to draft from a report that is None")
    normalised = _normalise(report)
    refusing = violations(normalised.fields())
    if refusing:
        return Refused(refusing)
    body = render.body(normalised)
    return Drafted(normalised, render.draft_text(body), body)


def _normalise(report: FeedbackReport) -> FeedbackReport:
    """Every text field with its home directories rewritten to ``~``.

    EVERY field, not only the narrative: a home path reaches the install coordinate through a
    project-local virtual environment and the step through a test's own file path, and a report that
    normalised only the sentences would be refused for the fields nobody thought to look at.
    """
    narrative = report.narrative
    attachments = report.attachments
    return report.with_fields(
        install=to_tilde(report.install),
        step=to_tilde(report.step),
        narrative=ProblemNarrative(
            to_tilde(narrative.did),
            to_tilde(narrative.happened),
            to_tilde(narrative.expected),
        ),
        attachments=Attachments(
            to_tilde(attachments.doctor_report),
            to_tilde(attachments.doctor_unavailable),
            to_tilde(attachments.structural_trace),
        ),
    )
