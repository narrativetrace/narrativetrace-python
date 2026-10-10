# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The pin — a structural trace promoted to a committed ``.approved.nt`` behind the user's yes — as
the four steps every skill that pins renders: approval mode on, run the suite and show, ask and
stop, promote. Mirrors Java's ``BaselinePin``.

INTENT: the verify skill pins a flow it checked and the debug skill pins the regression it fixed;
it is the same act on the same artifact behind the same gate
(:mod:`~narrativetrace_skills.catalogue.approval_gate`, the feedback skill's own words), so it is
written once.

**@llmNote** The approval run is the WHOLE suite, never the one test the skill ran: approval mode
compares every traced test, so a one-test run leaves every other traced test without a baseline
and the suite red (found by Java's trials; cross-port item 1 of Phase 7 milestone 2).
"""

from __future__ import annotations

from narrativetrace_skills.catalogue.approval_gate import (
    ANSWER_IS_THE_NEXT_MESSAGE,
    end_the_turn_on_the_question,
    never_edit_after_showing,
    never_in_the_turn_that_asked,
    show_the_whole_before_asking,
)
from narrativetrace_skills.catalogue.verify_commands import (
    APPROVAL_MODE_IS_ON,
    APPROVE,
    LIST_RECEIVED,
    RUN_THE_SUITE,
    RUN_THE_SUITE_FOR_REVIEW,
)
from narrativetrace_skills.skill import CommandStep, FailureNote, ReasonedRule, SkillStep

_BEFORE_THE_YES = (
    "Do not run narrativetrace-approve before the user says yes — promoting is the pinning."
)

ALWAYS: tuple[ReasonedRule, ...] = (
    show_the_whole_before_asking(
        ".received.nt",
        "the baseline becomes the contract every later change is held to, and a person can only "
        "approve what they have actually read",
    ),
    end_the_turn_on_the_question(_BEFORE_THE_YES),
)
"""The pin's always-rules: the whole review copy before the question, the question last."""

NEVER: tuple[ReasonedRule, ...] = (
    never_in_the_turn_that_asked("promote a baseline"),
    never_edit_after_showing(".received.nt", "promoted", "run is rendered"),
    ReasonedRule(
        rule="Never commit a .received.nt.",
        reason="it is the review copy; the committed contract is the .approved.nt",
    ),
)
"""The pin's never-rules, in the order the pages list them."""

_APPROVAL_MODE_ON = SkillStep(
    title="Turn approval mode on",
    body=CommandStep(commands=()),
    condition=(
        "if approval mode is off — nothing sets NARRATIVETRACE_APPROVAL or `approval = true`, or "
        "the doctor's config.approval-mode finding fails; when it is already on, go straight to "
        "the run"
    ),
    done=(
        "`pyproject.toml` carries `approval = true` under `[tool.narrativetrace]`, and "
        "`.gitignore` carries the line `*.received.nt` so a review copy is never committed"
    ),
    verify=APPROVAL_MODE_IS_ON,
    failure=(
        FailureNote(
            symptom="the verify still exits 1 after the edit",
            cause=(
                "the key sits under another table, the project also has a narrativetrace.toml "
                "(two configuration sources stop every run with DuplicateConfigurationError), or "
                "NARRATIVETRACE_APPROVAL=false is set in the environment, which wins over both"
            ),
            fix=(
                "keep one source — `approval = true` directly under `[tool.narrativetrace]`, or "
                "at the top of narrativetrace.toml — unset the variable, and run the verify again"
            ),
        ),
    ),
)

_REVIEW = SkillStep(
    title="Run the suite in approval mode and show every .received.nt",
    body=CommandStep(commands=(RUN_THE_SUITE_FOR_REVIEW, LIST_RECEIVED)),
    done=(
        "approval mode compares every traced test, not only the one this skill ran, so the run "
        "that writes the review copies is the whole suite; the first run of a test with no "
        "baseline fails on purpose — that failure is what writes its review copy — and the whole "
        "text of each .received.nt that run wrote is in the reply, not a summary of it — it holds "
        "names and shape and no value, which is why it is safe to commit once approved; where a "
        ".approved.nt already existed, the reply also names what the delta changed, by span id, "
        "in the program's own words, and whether it was meant"
    ),
)

_ASK = SkillStep(
    title="Ask once whether to pin it, then stop the turn",
    body=CommandStep(commands=()),
    done=(
        f"{ANSWER_IS_THE_NEXT_MESSAGE} {_BEFORE_THE_YES} Everything else — the report, every "
        "caveat, and what promoting does — goes before the question; the question is ONE "
        "sentence ending in a question mark and it is the reply's last line, so a reply whose "
        "last line is a sentence after the question has not asked it."
    ),
)

_PROMOTE = SkillStep(
    title="Promote what was shown, and nothing else",
    body=CommandStep(commands=(APPROVE,)),
    done=(
        "each .approved.nt now holds exactly the text that was shown and no .received.nt is left "
        "beside it — `git status --short test-narratives` lists the new or changed .approved.nt "
        "files and nothing else; those are what get committed — and the whole suite passes again "
        "after the promotion"
    ),
    verify=RUN_THE_SUITE,
)

STEPS: tuple[SkillStep, ...] = (_APPROVAL_MODE_ON, _REVIEW, _ASK, _PROMOTE)
"""The four pin steps, in order."""
