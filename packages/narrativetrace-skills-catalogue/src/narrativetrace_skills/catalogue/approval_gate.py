# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The approval gate every skill uses before it turns something it SHOWED into something durable or
public: show the whole artifact, ask once and end the turn on the question, act only on what was
shown. Mirrors Java's ``ApprovalGate``.

INTENT: the feedback skill files a public issue, and the verify and debug skills promote a
committed approval baseline; each is a person's decision, made on an artifact they read, in a turn
of their own. Written once — in the feedback skill's own words, which these functions reproduce
exactly — so every skill states the gate the same way, with only the artifact and the act filled
in. A rule restated by hand is a rule that drifts.
"""

from __future__ import annotations

from narrativetrace_skills.skill import ReasonedRule

ANSWER_IS_THE_NEXT_MESSAGE = (
    "the answer is the user's next message, never something assumed in this one."
)
"""Why the turn ends on the question — the clause every skill's version of that rule opens with."""


def show_the_whole_before_asking(artifact: str, why: str) -> ReasonedRule:
    """ "Show the whole <artifact> before asking anything", with this skill's reason."""
    return ReasonedRule(rule=f"Show the whole {artifact} before asking anything.", reason=why)


def end_the_turn_on_the_question(before_the_yes: str) -> ReasonedRule:
    """ "End the turn on the question" — followed by what must not happen before the yes, as a
    sentence naming this skill's own act."""
    return ReasonedRule(
        rule="End the turn on the question, with nothing after it.",
        reason=f"{ANSWER_IS_THE_NEXT_MESSAGE} {before_the_yes}",
    )


def never_in_the_turn_that_asked(act: str) -> ReasonedRule:
    """ "Never <act> in the turn that asked" — the yes is the user's next message."""
    return ReasonedRule(
        rule=f"Never {act} in the turn that asked.",
        reason="approval is the user's next message -- a yes assumed in the same turn is not one",
    )


def never_edit_after_showing(artifact: str, acted_on: str, changed: str) -> ReasonedRule:
    """ "Never edit the <artifact> after showing it" — what was approved is what is acted on.

    Args:
        artifact: what was shown, as the rule names it (``"draft"``).
        acted_on: the act in the past tense (``"filed"``).
        changed: what a change produces and how it is made again (``"report is drafted"``).
    """
    return ReasonedRule(
        rule=f"Never edit the {artifact} after showing it.",
        reason=(
            f"what was approved has to be what is {acted_on}, so a changed {changed} again and "
            "shown again"
        ),
    )
