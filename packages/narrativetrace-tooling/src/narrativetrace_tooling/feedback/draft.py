# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What drafting produced: either a report the gate cleared, with the two texts rendered from it, or
a refusal naming every rule that stood in the way.

Ports Java's sealed ``FeedbackDraft``. INTENT: a pair of distinct types rather than one draft
carrying a list of problems, so no caller can print a URL or write a body file while a violation
stands. :class:`Refused` has no body to file, by construction — not by convention.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace_tooling.feedback.check import ValueFreeViolation
from narrativetrace_tooling.feedback.report import FeedbackReport


@dataclass(frozen=True, slots=True)
class Refused:
    """The gate refused. Nothing was rendered and nothing may be written.

    :param violations: every rule that refused, field order then rule order; never empty
    """

    violations: tuple[ValueFreeViolation, ...]

    def __post_init__(self) -> None:
        if not self.violations:
            raise ValueError(
                "a refusal names what refused it — an empty violation list is a Drafted"
            )

    def describe(self) -> str:
        """The refusal, one line per violation, in the words the verb prints before exiting 2."""
        lines = "".join(f"  - {violation.describe()}\n" for violation in self.violations)
        return f"This report cannot be filed. {len(self.violations)} rule(s) refused it:\n{lines}"


@dataclass(frozen=True, slots=True)
class Drafted:
    """The gate cleared the report.

    :param report: the report AFTER home-path rewriting — what the two texts were rendered from
    :param draft: the whole report plus the privacy note: what the agent SHOWS
    :param body: the report alone, in Markdown: what gets filed, with nothing about the process
    """

    report: FeedbackReport
    draft: str
    body: str

    def __post_init__(self) -> None:
        if self.report is None or self.draft is None or self.body is None:
            raise TypeError("a drafted report carries its report and both texts")
        if self.body not in self.draft:
            raise ValueError(
                "the draft must contain the body verbatim — a person who approves the draft is"
                " approving what gets filed, byte for byte"
            )


FeedbackDraft = Drafted | Refused
"""What :func:`~narrativetrace_tooling.feedback.drafter.draft` returns. A caller narrows it with
``isinstance``; there is no third case, and mypy's exhaustiveness checking is what keeps that true.
"""
