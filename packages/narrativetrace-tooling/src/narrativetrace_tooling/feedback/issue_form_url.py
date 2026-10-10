# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The pre-filled issue-form URL — the default way a report is filed, and the only one that needs no
tool installed and no credential held by anybody but the person clicking it.

Ports Java ``IssueFormUrl``. INTENT (design D1 as ruled): the user opens this in their own browser,
where they are already signed in, and submits it themselves. That click is the approval and the
authentication at once, which is why there is no endpoint, no token and nothing for an agent to
hold. The agent prints the URL; it never opens it.

**@llmNote** The BODY is deliberately not in the URL. A doctor report and a structural trace are
kilobytes, a URL that is too long answers ``414 URI Too Long``, and the limit is undocumented — so
the long fields live in the body file and the user pastes them. What travels in the URL is the
short, searchable half: the category, the install coordinate, the step, the language, the agent.

**@llmNote** ``labels`` only takes effect for someone with push access ("labels are silently dropped
otherwise"), so for an outside reporter the parameter is harmless and inert. It is here because the
same label set is what the ``gh`` path applies, and two label lists that could disagree would be two
triage queues.

**@llmNote** Every parameter name other than ``template``, ``title`` and ``labels`` must be a
field ``id`` the form declares: the host documents the ``id`` as "the canonical identifier for the
field in URL query parameter prefills" and SILENTLY IGNORES a parameter naming one the form does not
have. A renamed field fails nowhere and just opens a form with empty boxes, which is why
``tests/feedback/test_issue_form_fields.py`` holds the two together.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

from narrativetrace_tooling.feedback import public_repository
from narrativetrace_tooling.feedback.report import FeedbackReport

MAX_LENGTH: Final = 4_000
"""The length this URL is kept under.

GitHub answers ``414 URI Too Long`` past an undocumented limit, so the budget is a conservative one
we set ourselves and measure, rather than one we discover from a user's failure."""

TRUNCATION_MARKER: Final = " … (continued in the pasted body)"
"""What a field that did not fit ends with, so a reader knows the rest is in the body file."""

_FIELD_LIMIT: Final = 400
"""Per-field ceiling before the whole-URL budget is enforced."""

_MINIMUM_FIELD_LIMIT: Final = 16
"""Where halving the per-field ceiling stops. Below this a clipped field says nothing at all, and
the budget is met by the short fields alone."""

_BASE: Final = f"https://github.com/{public_repository.SLUG}/issues/new"


def issue_form_url(report: FeedbackReport) -> str:
    """The pre-filled URL for this report, inside :data:`MAX_LENGTH`.

    :raises ValueError: when the report is not a Python report
    """
    public_repository.require_this_runtime(report)
    limit = _FIELD_LIMIT
    url = _build(report, limit)
    while len(url) > MAX_LENGTH and limit > _MINIMUM_FIELD_LIMIT:
        limit //= 2
        url = _build(report, limit)
    assert stays_under_budget(url), "the issue-form URL must stay inside its own budget"
    return url


def stays_under_budget(url: str) -> bool:
    """Whether a built URL is inside the budget — :func:`issue_form_url`'s own postcondition."""
    return len(url) <= MAX_LENGTH


def _build(report: FeedbackReport, field_limit: int) -> str:
    parameters = {
        "template": public_repository.FORM,
        "title": _clip(public_repository.title_for(report), field_limit),
        "labels": ",".join(public_repository.labels_for(report)),
        "runtime": _clip(report.runtime, field_limit),
        "category": report.category.id,
        "install": _clip(report.install, field_limit),
        "step": _clip(report.step, field_limit),
        "language": _clip(report.language, field_limit),
        "agent": _clip(report.agent.describe(), field_limit),
    }
    query = "&".join(f"{name}={_encode(value)}" for name, value in parameters.items())
    return f"{_BASE}?{query}"


def _encode(value: str) -> str:
    """Percent-encoding with the space written ``%20`` rather than ``+``.

    ``urlencode`` implements HTML form encoding, where a space is ``+``; that is right inside a form
    POST and wrong inside a query a browser hands to the host's prefill reader, which would show the
    plus signs.
    """
    return quote(value, safe="")


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit] + TRUNCATION_MARKER
