# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace-verify`` — reads what a change actually did before the agent says it is done,
and pins the result as an approval baseline behind the user's yes. Mirrors Java's
``NarrativeTraceVerifySkill`` on this runtime's capture (the pytest plugin's ``narrative_trace``
fixture), artifacts (``narrative-traces/``) and approve verb (``narrativetrace-approve``).

The loop runs after the tests are green and before the report: decide whether the change is worth
tracing and say so (a pure function is not); write the intent down BEFORE the run, because a trace
read against nothing confirms whatever happened; run the smallest real path; read the value-free
structural trace against the intent; open values only on the span that looks wrong; fix and
re-read; pin; report what the trace showed, citing span ids.

The pin is :mod:`~narrativetrace_skills.catalogue.baseline_pin`, behind the feedback skill's own
gate wording (:mod:`~narrativetrace_skills.catalogue.approval_gate`).

**@llmNote** This skill declares NO allowed tools, and that is a safety property: the promotion
runs through ``uv``, so pre-approving ``uv`` would pre-approve the promotion in the turn the gate
says must stop. :func:`~narrativetrace_skills.lints.promotion_not_pre_approved` fails the build if
one is ever added.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue import baseline_pin
from narrativetrace_skills.catalogue.trace_reading import (
    CITE_SPAN_IDS,
    FLAVOURS,
    NEVER_REDACTION_OFF,
    SHAPES,
)
from narrativetrace_skills.catalogue.verify_commands import (
    LIST_NARRATIVES,
    LIST_STRUCTURAL,
    RUN_THE_PATH,
)
from narrativetrace_skills.skill import (
    CommandStep,
    FailureNote,
    ReasonedRule,
    Skill,
    SkillStep,
    SnippetStep,
)

ONLY_ON_A_MISMATCH = (
    "only when the structural read named a span that does not match the intent; otherwise go on "
    "to the pin"
)
"""Values, the fix and the re-read happen only when the structural read found a mismatch."""

FLOW_TEST = "examples/sixty_seconds/test_place_order_flow.py"
"""The smallest test that drives a real path through its collaborators, traced."""

_DECIDE = SkillStep(
    title="Decide whether to trace, and say so",
    body=CommandStep(commands=()),
    done=(
        "before anything runs, the reply says which it is: 'tracing: <the reason>' when the change "
        "crosses two or more collaborators over a boundary, branches, retries, runs async or "
        "concurrently, carries state between calls, touched more call sites than it added, or "
        "includes code not written in this session; or 'skipping narrativetrace-verify: <a pure "
        "function | a one-class edit with no collaborator | a flow one test already walks end to "
        "end>' — a skip ends the skill here, and that sentence is the report. A whole flow's .nt "
        "is dozens of lines: cheap where the path is not obvious, waste where it is"
    ),
)

_INTENT = SkillStep(
    title="Write the intent down before running anything",
    body=CommandStep(commands=()),
    done=(
        "three to six lines in the reply, under the word Intent, written before the first traced "
        "run: which collaborators the change touches, in which order, under which branch, how "
        "many times — the oracle the trace is read against, never edited after the run"
    ),
)

_RUN = SkillStep(
    title="Run the smallest real path with tracing on",
    body=SnippetStep(path=FLOW_TEST, language="python"),
    condition=(
        "the project already has a test that drives the changed path through its real "
        "collaborators, each wrapped with the narrative_trace fixture: run that one — again, if "
        "it already ran: a trace from a run made before the Intent was written does not count; "
        "otherwise write the smallest one, as below"
    ),
    done=(
        "the test passed and its .nt was written under narrative-traces/structural/ by this run, "
        "after the Intent"
    ),
    verify=RUN_THE_PATH,
    failure=(
        FailureNote(
            symptom="no .nt for the test appears under narrative-traces/structural",
            cause=(
                "the test does not request the narrative_trace fixture, the collaborators on the "
                "path are not wrapped with it, or the pytest plugin is not registered"
            ),
            fix="run narrativetrace-doctor and apply its fix, then run the test again",
        ),
    ),
)

_READ = SkillStep(
    title="Read the structural trace first, against the intent",
    body=CommandStep(commands=(LIST_STRUCTURAL,)),
    done=(
        "the .nt of the test just run was opened and read whole before any value was looked at, "
        "and the reply walks it against the intent — calls, order, branch, multiplicity — naming "
        "every match and every mismatch by its span id (#2.1); the shapes below are the checklist"
    ),
)

_VALUES = SkillStep(
    title="Open values on the span that looks wrong, and only there",
    body=CommandStep(commands=(LIST_NARRATIVES,)),
    condition=ONLY_ON_A_MISMATCH,
    done=(
        "only the flagged span was read in the .md narrative, found by the id the .nt gave it — "
        "not the whole file; a [REDACTED] value stays redacted"
    ),
)

_FIX = SkillStep(
    title="Fix, re-run, read again",
    body=CommandStep(commands=(RUN_THE_PATH,)),
    condition=ONLY_ON_A_MISMATCH,
    done=(
        "the same test ran again after the fix and its new .nt was read whole: the span that was "
        "wrong now matches the intent, and a fix that changed the shape was read again from the "
        "structural read"
    ),
)

_REPORT = SkillStep(
    title="Report what the trace showed",
    body=CommandStep(commands=()),
    done=(
        "two sentences on what the trace showed, every claim citing the span id it rests on — a "
        "claim without an id is not a claim, and only ids in the .nt that was read count — with "
        "the .nt attached or quoted; 'tests pass' alone is not the report"
    ),
)

NARRATIVETRACE_VERIFY = Skill(
    canonical_name="narrativetrace-verify",
    skill_class="guided",
    description=(
        "Verifies a change in a Python project by reading what the code actually did before "
        "saying it is done. Use after the tests are green and before reporting a change that "
        "crosses collaborators, branches, retries, runs async, carries state between calls, or "
        "touches code not written in this session -- and skip it, saying why, for a pure "
        "function or a one-class edit. Writes the intent down first, runs the smallest real path "
        "with NarrativeTrace on, reads the value-free structural trace against the intent, opens "
        "values only on the span that looks wrong, fixes and re-reads, then pins the flow as an "
        "approval baseline behind your yes and reports what the trace showed, citing span ids. "
        "Say 'verify this change with the trace', 'check what the code actually did', 'did the "
        "flow do what I meant', or 'pin this flow as a baseline' to invoke it."
    ),
    when_to_use=(
        "Non-obvious triggers: the suite is green but the change touched more call sites than it "
        "added; a notification, payment or retry path changed; a .received.nt appeared after a "
        "test run; you are about to write 'tests pass' as the whole report."
    ),
    fixture="examples/sixty_seconds",
    allowed_tools=(),
    steps=(_DECIDE, _INTENT, _RUN, _READ, _VALUES, _FIX, *baseline_pin.STEPS, _REPORT),
    always=(
        CITE_SPAN_IDS,
        ReasonedRule(
            rule="Use the cheapest flavour that answers the question.",
            reason=(
                "the structural trace first and a value on one span only is what keeps the "
                "common case near zero tokens"
            ),
        ),
        *baseline_pin.ALWAYS,
    ),
    never=(
        ReasonedRule(
            rule="Never report a change as done on green tests alone once this skill decided to "
            "trace.",
            reason=(
                "the suite checks what someone thought to assert; the trace shows what the code did"
            ),
        ),
        ReasonedRule(
            rule="Never read a trace against nothing.",
            reason=(
                "an intent written after the run bends to whatever happened — that is why it "
                "comes first"
            ),
        ),
        NEVER_REDACTION_OFF,
        *baseline_pin.NEVER,
    ),
    sections=(FLAVOURS, SHAPES),
)
