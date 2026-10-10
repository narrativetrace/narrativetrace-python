# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace feedback`` — the value-free gate between a problem report about NarrativeTrace
and a leaked secret, and the two channels a report may be filed through.

INTENT: there is no endpoint, no private inbox and no credential anybody holds. The agent drafts the
report, shows it whole, and asks once; the person files it themselves, in a browser they are already
signed in to — that click is the approval and the authentication at once. So every report is PUBLIC
from the first second, which is why the gate is the hard one and runs first.

**The runtime's deny-list is reused, never copied — and that is kept by an ASSERTION, not by a
dependency.** This distribution declares zero dependencies and its own architecture gate
(``tests/test_architecture.py``) forbids importing ``narrativetrace`` at all: the edge would be a
cycle, since the ``narrativetrace`` distribution depends on THIS one. So
:mod:`narrativetrace_tooling.feedback.vocabulary` restates the vocabulary as data, and
``narrativetrace-security-tests`` — the one package that may see both — asserts over the shared
corpus that every name and every value shape the renderer redacts is also refused here. The
implication is asserted ONE way, deliberately: the gate is a strict superset, because a false
positive here is a refusal that names its rule and a false negative is a public issue.

**@llmNote** What this module re-exports IS the surface an ENTRY POINT needs: gather what a project
can tell you, draft (which normalises, gates and renders, in that order), and print one of the two
channels. The modules behind it are free to move. The one deliberate exception is the cross-layer
assertion in ``narrativetrace-security-tests``, which reaches into
:mod:`narrativetrace_tooling.feedback.rules` and :mod:`~narrativetrace_tooling.feedback.matchers` by
name — it is asserting about those internals, across a boundary no dependency may cross, which is
the whole reason it exists.

Reached through the ``narrativetrace`` console script.
"""

from __future__ import annotations

from narrativetrace_tooling.feedback.check import (
    DOCTOR_REPORT_FIELD,
    ValueFreeViolation,
    rules_refusing,
    violations,
)
from narrativetrace_tooling.feedback.draft import Drafted, FeedbackDraft, Refused
from narrativetrace_tooling.feedback.drafter import draft
from narrativetrace_tooling.feedback.gatherer import (
    INSTALL_UNKNOWN,
    TraceChoice,
    attachments_for,
    choose_trace,
    install_coordinate,
)
from narrativetrace_tooling.feedback.gh_command_line import gh_command_line
from narrativetrace_tooling.feedback.home_paths import to_tilde
from narrativetrace_tooling.feedback.issue_form_url import MAX_LENGTH, issue_form_url
from narrativetrace_tooling.feedback.public_repository import FORM, RUNTIME, SLUG, labels_for
from narrativetrace_tooling.feedback.render import PRIVACY_NOTE
from narrativetrace_tooling.feedback.report import (
    AgentIdentity,
    Attachments,
    FeedbackCategory,
    FeedbackReport,
    ProblemNarrative,
)
from narrativetrace_tooling.feedback.rules import ALL_RULES, ValueFreeRule
from narrativetrace_tooling.feedback.structural_trace import looks_structural

__all__ = [
    "ALL_RULES",
    "DOCTOR_REPORT_FIELD",
    "FORM",
    "INSTALL_UNKNOWN",
    "MAX_LENGTH",
    "PRIVACY_NOTE",
    "RUNTIME",
    "SLUG",
    "AgentIdentity",
    "Attachments",
    "Drafted",
    "FeedbackCategory",
    "FeedbackDraft",
    "FeedbackReport",
    "ProblemNarrative",
    "Refused",
    "TraceChoice",
    "ValueFreeRule",
    "ValueFreeViolation",
    "attachments_for",
    "choose_trace",
    "draft",
    "gh_command_line",
    "install_coordinate",
    "issue_form_url",
    "labels_for",
    "looks_structural",
    "rules_refusing",
    "to_tilde",
    "violations",
]
