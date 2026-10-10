# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Reports a defect in NarrativeTrace itself, with the user's approval and nothing else.

The shape is the whole point: draft, SHOW the draft in full, ask one question, stop the turn —
the gate :mod:`~narrativetrace_skills.catalogue.approval_gate` states once for every skill that
turns something it showed into something durable or public.
Filing is public and permanent, so the decision has to be the user's, in a turn of their own --
not inferred from the turn that asked, and not from a summary of a report they never saw.

**@llmNote** This skill declares NO allowed tools, and that is a safety property rather than an
omission. A Claude-flavour ``allowed-tools`` grants its listed tools for the turn that loads the
skill, without prompting -- so a skill that declared ``uv`` would pre-approve its own reporting
command. :func:`narrativetrace_skills.lints.publishing_not_pre_approved` fails the build if that is
ever added back.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue.approval_gate import (
    end_the_turn_on_the_question,
    never_edit_after_showing,
    never_in_the_turn_that_asked,
    show_the_whole_before_asking,
)
from narrativetrace_skills.catalogue.doctor_commands import DOCTOR_REPORT_WELL_FORMED
from narrativetrace_skills.catalogue.feedback_commands import (
    DRAFT_FILES_WRITTEN,
    DRAFT_REPORT,
    PRINT_URL,
    SHOW_DRAFT,
    URL_PRINTED,
)
from narrativetrace_skills.skill import CommandStep, FailureNote, ReasonedRule, Skill, SkillStep

NARRATIVETRACE_FEEDBACK = Skill(
    canonical_name="narrativetrace-feedback",
    skill_class="guided",
    description=(
        "Reports a defect in NarrativeTrace itself -- the library, the doctor, an agent skill, or "
        "the published install prompt. Use when a doctor finding is wrong or its fix does not "
        "work, when a skill step cannot be followed or its verify cannot be met, when the install "
        "prompt is wrong, or when the library misbehaves and the project is configured "
        "correctly. Drafts the report from this project (the install coordinates, the doctor's "
        "own JSON report, and at most one structural trace), refuses to write one that carries a "
        "value from your traces and names the rule that refused it, shows you the whole draft, "
        "and then asks once whether to file it publicly. Files nothing without your answer and "
        "sends nothing anywhere. Say 'report this to NarrativeTrace', 'the doctor's fix did not "
        "work', or 'file a bug about this skill' to invoke it."
    ),
    when_to_use=(
        "Non-obvious triggers: a doctor fix that leaves the same finding failing; a skill step "
        "whose verify cannot be met on a correctly configured project; wording in the install "
        "prompt that led somewhere wrong."
    ),
    fixture="examples/sixty_seconds",
    allowed_tools=(),
    steps=(
        SkillStep(
            title="Gather what the report needs",
            # `|| true`: a failing finding is the doctor working correctly -- it is usually WHY
            # there is something to report.
            body=CommandStep(commands=("uv run narrativetrace doctor || true",)),
            verify=DOCTOR_REPORT_WELL_FORMED,
            failure=(
                FailureNote(
                    symptom="the CLI is not found, or the project has no pyproject.toml",
                    cause="NarrativeTrace is not installed in this project's environment",
                    fix=(
                        "report under the prompt or library category instead -- those do not need "
                        "a doctor report"
                    ),
                ),
            ),
        ),
        SkillStep(
            title="Draft the report and let the gate check it",
            body=CommandStep(commands=(DRAFT_REPORT,)),
            verify=DRAFT_FILES_WRITTEN,
            failure=(
                FailureNote(
                    symptom="the command exits 2 naming a vf.* rule",
                    cause=(
                        "a field carries a value from this project's own run -- a rendered call "
                        "line, an elapsed time, a credential-shaped string, an address"
                    ),
                    fix=(
                        "rewrite that one field to describe what happened instead of pasting it, "
                        "and draft again; never work around the rule by moving the text to "
                        "another field"
                    ),
                ),
            ),
        ),
        SkillStep(
            title="Show the whole draft, not a summary of it",
            body=CommandStep(commands=(SHOW_DRAFT,)),
            # No verify: judgmental -- replay confirms the file prints, not that the reply
            # carries all of it. The Always rules below carry the condition.
        ),
        SkillStep(
            title="Ask once whether to file it, then stop the turn",
            body=CommandStep(commands=()),
            # No verify: a decision, not a command. The answer is the user's next message.
        ),
        SkillStep(
            title="Print the way to file it, and nothing else",
            body=CommandStep(commands=(PRINT_URL,)),
            verify=URL_PRINTED,
        ),
    ),
    always=(
        show_the_whole_before_asking(
            "draft",
            "filing is public and permanent, and a person can only approve what they have "
            "actually read",
        ),
        end_the_turn_on_the_question(
            "Do not print the issue URL or run gh before the user says yes — showing the URL is "
            "the filing."
        ),
        ReasonedRule(
            rule="Ask in the user's own language.",
            reason=(
                "the report may be written in any language, and a question nobody understands is "
                "not a question"
            ),
        ),
        ReasonedRule(
            rule=(
                "Tell the user that filing is public, under their own account, before they answer."
            ),
            reason=(
                "a public issue shows that their project uses NarrativeTrace, and that is their "
                "decision to make knowingly"
            ),
        ),
        ReasonedRule(
            rule="With the printed URL, name the file to paste and where.",
            reason=(
                "the URL carries the short fields only; the body is never in it, so the user "
                "must paste the body file the verb names into the form's last box"
            ),
        ),
    ),
    never=(
        ReasonedRule(
            rule="Never attach a rendered trace, a log file or a source file.",
            reason=(
                "those carry the values from the user's own run; the structural trace carries "
                "the same shape of the same call without any of them, and the verb attaches it "
                "on its own"
            ),
        ),
        never_in_the_turn_that_asked("file"),
        never_edit_after_showing("draft", "filed", "report is drafted"),
        ReasonedRule(
            rule="Never open the URL or run the printed command.",
            reason=(
                "submitting is the user's act, in their own browser or their own shell, under "
                "their own account"
            ),
        ),
        ReasonedRule(
            rule="Never route a rule's refusal around the gate.",
            reason=(
                "a field that cannot be filed is a field to rewrite, not to move somewhere the "
                "rule does not look"
            ),
        ),
    ),
)
