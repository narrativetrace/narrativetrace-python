# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Diagnosis only. ``add-narrative-tracing`` owns getting a project to a first trace (install,
wrap, render, send to a logger); this skill starts from "something is already wired up" and runs
the tested CLI, reads its report, and points at the fix for whichever finding failed."""

from __future__ import annotations

from narrativetrace_skills.catalogue.doctor_commands import (
    APPROVAL_FLOW_DIFF,
    DOCTOR_REPORT_WELL_FORMED,
    OPEN_NEWEST_RENDERED_TRACE,
    REDACTION_PROOF_FINDING_PRESENT,
    REDACTION_TEST_GUIDANCE,
)
from narrativetrace_skills.skill import CommandStep, FailureNote, ReasonedRule, Skill, SkillStep

_FIXTURE = "examples/sixty_seconds"

NARRATIVETRACE_DOCTOR = Skill(
    canonical_name="narrativetrace-doctor",
    claude_segment="doctor",
    skill_class="mechanical",
    description=(
        "Diagnoses a NarrativeTrace Python install and configuration. Use when nothing is being "
        "traced, no trace output files appear, DuplicateConfigurationError shows up on startup, "
        "a *args method's parameters render as one args: [...] value, or you are not sure "
        "NarrativeTrace is wired up correctly. Checks the interpreter and pytest versions, that "
        "all eight narrativetrace-* packages agree on one version, NARRATIVETRACE_OUTPUT, that "
        "the pytest plugin is registered and not disabled, unrecognized narrativetrace.toml "
        "keys, an imported-but-unused not_traced_field/__nt_not_traced__ marker, whether "
        "redaction is proven in a test, and stale approval-trace diffs. Read-only -- makes no "
        "changes. Say 'check my narrativetrace setup', 'is narrativetrace broken', or 'why isn't "
        "anything being traced' to invoke it."
    ),
    when_to_use=(
        "A project already has NarrativeTrace installed and something about it is not working, "
        "or an agent wants a pre-flight check before wiring it into new code."
    ),
    fixture=_FIXTURE,
    allowed_tools=("uv", "git"),
    steps=(
        SkillStep(
            title="Run the doctor and read its report",
            # `|| true`: a failing finding is doctor working correctly (there is something to
            # act on), never a crash -- the mechanical floor this step's own verify checks is
            # well-formedness, not that every finding passed.
            body=CommandStep(commands=("uv run narrativetrace doctor || true",)),
            verify=DOCTOR_REPORT_WELL_FORMED,
            failure=(
                FailureNote(
                    symptom="the CLI's JSON output does not parse, or is missing findings",
                    cause="the CLI crashed instead of reporting a finding",
                    fix=(
                        "re-run `uv run narrativetrace doctor --json` directly and read the raw "
                        "output -- a crash here is a doctor bug, never a project finding"
                    ),
                ),
            ),
        ),
        SkillStep(
            title="Prove redaction in a test",
            body=CommandStep(commands=(REDACTION_TEST_GUIDANCE,)),
            verify=REDACTION_PROOF_FINDING_PRESENT,
            failure=(
                FailureNote(
                    symptom="not_traced_field/__nt_not_traced__ is present but never applied",
                    cause="trusting redaction by inspection instead of proving it in a test",
                    fix=(
                        "render a call with a deny-listed parameter name and assert the output "
                        'contains "[REDACTED]"'
                    ),
                ),
            ),
        ),
        SkillStep(
            title="Read the rendered trace before asserting",
            body=CommandStep(commands=(OPEN_NEWEST_RENDERED_TRACE,)),
            # No verify: judgmental -- replay confirms the command runs cleanly (its own exit
            # code), not that reading a rendered trace changed anything about the code written
            # next.
        ),
        SkillStep(
            title="Approval flow: diff the structural trace, not just values",
            body=CommandStep(commands=(APPROVAL_FLOW_DIFF,)),
            flag="unstudied -- eval cell pending",
        ),
    ),
    always=(
        ReasonedRule(
            rule="Run the doctor CLI and read its report before making any change.",
            reason=(
                "the tested tooling already computed the finding -- re-deriving it by hand "
                "risks disagreeing with what ships"
            ),
        ),
    ),
    never=(
        ReasonedRule(
            rule="Never have this skill edit, generate, or delete a file.",
            reason=(
                "narrativetrace-doctor is scoped read-only by design -- generation of the "
                "redaction-proof test itself is a separate, later skill"
            ),
        ),
        ReasonedRule(
            rule="Never claim a finding passed without having run the doctor CLI in this session.",
            reason=(
                "self-reported success overstates reality -- a build claimed green that does "
                "not reproduce from clean is not evidence; verify is never 'ask the agent'"
            ),
        ),
    ),
)
