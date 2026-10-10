# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Where a Python problem report is filed, the one form it is filed through, and the labels triage
sorts on.

Ports Java ``PublicRepository``. INTENT: one place, so the issue-form URL and the ``gh`` line
cannot name different repositories or different templates. Every runtime in the family has its own
repository and the SAME form file name — the form is a cross-runtime artifact, the repository is
not.

**@llmNote** :func:`require_this_runtime` exists because a wrong answer here is unfixable in public:
a report filed into this tracker from another runtime's project is a public issue in the wrong
repository, and deleting it does not un-publish it. The report's own runtime field is checked rather
than assumed.
"""

from __future__ import annotations

from typing import Final

from narrativetrace_tooling.feedback.report import FeedbackReport

SLUG: Final = "narrativetrace/narrativetrace-python"
"""The public Python repository, ``owner/name``."""

FORM: Final = "narrativetrace-report.yml"
"""The issue form every runtime's repository carries under ``.github/ISSUE_TEMPLATE/``."""

RUNTIME: Final = "python"
"""The runtime this library files for, and the value of the ``runtime:`` label."""

_LABEL_LIMIT: Final = 50
"""The longest a GitHub label name may be. A label built past this is one the host refuses, so
building it is never the right answer — and an unbounded label is also how a long language tag got
into a URL that then blew its own length budget from inside the one parameter nothing clipped."""


def require_this_runtime(report: FeedbackReport) -> None:
    """:raises ValueError: when the report is not a Python report."""
    if report.runtime != RUNTIME:
        raise ValueError(
            f"this library files into {SLUG}, and the report's runtime is {report.runtime!r} —"
            " file it through that runtime's own tooling"
        )


def labels_for(report: FeedbackReport) -> tuple[str, ...]:
    """The labels triage sorts on, in a stable order, each inside the platform's own length limit.

    **@llmNote** No ``agent:<product>`` label, deliberately. The agent product is free text as the
    agent reported it, so a label built from it is a label set strangers extend — and labels from a
    reporter without push access are silently dropped anyway. The agent line travels as a FIELD,
    where it is searchable and harmless.
    """
    return tuple(
        label[:_LABEL_LIMIT]
        for label in (
            "from-agent",
            f"runtime:{report.runtime}",
            f"category:{report.category.id}",
            f"lang:{report.language}",
        )
    )


def title_for(report: FeedbackReport) -> str:
    """The issue title: the category, then the step it happened at."""
    return f"{report.category.id}: {report.step}"
