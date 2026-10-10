# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace-debug`` — finds the cause of a symptom by reading what the code did with the
values, fixes it where it diverged, and pins the reproduction behind the user's yes. Mirrors Java's
``NarrativeTraceDebugSkill`` on this runtime's capture, artifacts and approve verb.

The loop starts from a symptom, not a change: reproduce it with the smallest input and tracing on;
across threads or tasks read the sequence diagram first; name, by span id, the first span whose
inputs are right and whose result is wrong — before touching code; narrow to that span's sub-tree
by wrapping one more collaborator, never by redacting; hand a defect in NarrativeTrace itself to
``narrativetrace-feedback`` instead of patching around it; fix it in that span, re-run the same
input, and check the structural trace shows nothing else moved; keep the reproduction as the
regression test and pin its structural trace (:mod:`~narrativetrace_skills.catalogue.baseline_pin`);
report the root cause by span id.

Unlike ``narrativetrace-verify`` there is no cost rule that skips the trace: once there is a bug,
the trace is the cheap way to find it. The cost rule here is only "narrow the span before you read
values". Both skills render the same :mod:`~narrativetrace_skills.catalogue.trace_reading`
sections, and reproduce on the same fixture listing.

**@llmNote** No allowed tools, for the verify skill's reason: the pin promotes through ``uv``
(:func:`~narrativetrace_skills.lints.promotion_not_pre_approved`). In this runtime
``not_traced_field``, ``__nt_not_traced__`` and the ``@not_traced`` parameter decorator REDACT a
value — none of them scopes a trace — which is why the bisect step narrows by wrapping one more
collaborator with ``trace_object`` instead. A red run here writes the ``.md`` and ``.mmd`` but no
``.nt`` (the ``.nt`` on disk is the last green one), so "the shape before the fix" comes from the
red run's ``.md`` call lines.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue import baseline_pin
from narrativetrace_skills.catalogue.debug_commands import LIST_DIAGRAMS, REPRODUCE
from narrativetrace_skills.catalogue.narrativetrace_verify import FLOW_TEST
from narrativetrace_skills.catalogue.trace_reading import (
    CITE_SPAN_IDS,
    FLAVOURS,
    NEVER_REDACTION_OFF,
    SHAPES,
)
from narrativetrace_skills.catalogue.verify_commands import LIST_NARRATIVES, LIST_STRUCTURAL
from narrativetrace_skills.skill import (
    CommandStep,
    FailureNote,
    ReasonedRule,
    Skill,
    SkillStep,
    SnippetStep,
)

_REPRODUCE = SkillStep(
    title="Reproduce the symptom with tracing on",
    body=SnippetStep(path=FLOW_TEST, language="python"),
    condition=(
        "a test already drives the path with the input from the symptom, run that one; otherwise "
        "write the smallest one, as below — the reported input, through the real collaborators "
        "each wrapped with trace_object and the narrative_trace fixture, asserting the value the "
        "symptom says should have come out"
    ),
    done="the test ran with the reported input, and its .md narrative was written by this run",
    verify=REPRODUCE,
    failure=(
        FailureNote(
            symptom="no .md for the test appears under narrative-traces/traces",
            cause=(
                "the test does not request the narrative_trace fixture, the collaborators on the "
                "path are not wrapped with it, or the pytest plugin is not registered"
            ),
            fix="run narrativetrace-doctor and apply its fix, then run the test again",
        ),
    ),
)

_SYMPTOM = SkillStep(
    title="Find the symptom in the values",
    body=CommandStep(commands=(LIST_NARRATIVES,)),
    done=(
        "the reported value is in this run's .md narrative, or the reproducing test fails on it — "
        "a symptom that does not reproduce is said so, and the loop stops here"
    ),
)

_DIAGRAM = SkillStep(
    title="Across threads, read the sequence diagram first",
    body=CommandStep(commands=(LIST_DIAGRAMS,)),
    condition=(
        "only when the path crosses threads or tasks — the .nt shows a fork, async or "
        "fire-and-forget marker — or the symptom is about order (a call that ran before or after "
        "another); otherwise go straight to localizing"
    ),
    done=(
        "the reproduction's .mmd was read before any span's values, and the reply says which call "
        "ran before which across the threads, by the span id in each call's note — the span it "
        "points to is the one localized next"
    ),
)

_LOCALIZE = SkillStep(
    title="Localize by reading: name the first span where a value diverges",
    body=CommandStep(commands=()),
    done=(
        "the reproduction's .md spans were read from the root down until the first one whose "
        "inputs are what the symptom implies but whose result, the value it passes on, or the "
        "branch it takes is not; the reply names that span by its id (#1.3) and the boundary — "
        "the collaborator, the parameter or return, the value that arrived and the value that "
        "left — before any code is changed: by reading, not by stepping through a debugger or "
        "adding prints"
    ),
)

_BISECT = SkillStep(
    title="Bisect by span, not by file",
    body=CommandStep(commands=(REPRODUCE,)),
    condition=(
        "only when the value went into the diverging span right and came out wrong, and what "
        "happens in between is more than that span's own few lines; otherwise the diverging span "
        "is the defect — go on to the fix"
    ),
    done=(
        "only the sub-tree under the diverging id was read on each re-run — the spans whose id "
        "begins with it (#1.3, #1.3.1, #1.3.2) — and where the work inside that span is not "
        "traced, the collaborator it calls was wrapped with trace_object in the reproducing test, "
        "as the listing above wraps its inventory, and the run repeated, until the divergence "
        "sits in the smallest span that has it; never not_traced_field, __nt_not_traced__ or "
        "@not_traced to narrow — in Python they redact a value, they do not scope a trace"
    ),
)

_HAND_OFF = SkillStep(
    title="Hand a defect in NarrativeTrace itself to narrativetrace-feedback",
    body=CommandStep(commands=()),
    condition=(
        "only when the trace and the code disagree — a call the code makes has no span, a span "
        "shows a value the code did not pass, one span has two ids in two flavours — or the "
        "diverging span is inside NarrativeTrace; otherwise go on to the fix"
    ),
    done=(
        "narrativetrace-feedback was started with the span id and the value-free .nt — never a "
        "value from the trace — and the project's code was not changed to work around it; the "
        "loop ends with that hand-off"
    ),
)

_FIX = SkillStep(
    title="Fix it in the diverging span, re-run the same input, read the same span",
    body=CommandStep(commands=(REPRODUCE,)),
    done=(
        "the change is in the code of that span — the method the diverging id names, or what it "
        "calls — and the reproducing test passes; the same span, by the same id, now carries the "
        "value the symptom implied; a change anywhere else that makes the test pass silences the "
        "symptom and leaves the defect, so it is undone"
    ),
    verify=REPRODUCE,
)

_DELTA = SkillStep(
    title="Check that nothing else moved",
    body=CommandStep(commands=(LIST_STRUCTURAL,)),
    done=(
        "the fixed run's .nt was read whole and compared, line by line, with the call lines of the "
        "reproduction's .md — a red run writes no .nt (the .nt on disk is the last green one), so "
        "the shape before the fix is the .md's calls and ids without their values: the same calls "
        "in the same order under the same ids; a value fix moves no line of a value-free trace, "
        "and every line that did move is named by its id in the reply and either explained by the "
        "fix or undone"
    ),
)

_KEEP = SkillStep(
    title="Keep the reproduction as the regression test",
    body=CommandStep(commands=()),
    done=(
        "the reproducing test stays in the suite with the input from the symptom and asserts the "
        "value the fixed span now carries — not only that nothing raises — so it fails when the "
        "fix is undone; its structural trace is what the pin below makes the baseline"
    ),
)

_REPORT = SkillStep(
    title="Report the root cause as the trace showed it",
    body=CommandStep(commands=()),
    done=(
        "the root cause in the user's own terms — the span id where it diverged, the value that "
        "arrived and the value that left, the branch it took — and what the fix changed in that "
        "span; every claim cites the span id it rests on, from the .nt or .md read in this "
        "session: a claim without an id is not a claim. The report is written in full before the "
        "pin question, where the gate puts it, and the closing reply after the promotion names "
        "the span id again in its one-line summary of the cause"
    ),
)

NARRATIVETRACE_DEBUG = Skill(
    canonical_name="narrativetrace-debug",
    skill_class="guided",
    description=(
        "Finds the cause of a wrong result in a Python project by reading what the code did with "
        "the values, not by stepping through it. Use when a symptom is reported -- a wrong "
        "amount, a wrong id, a call in the wrong order, a test that fails with a value nobody "
        "expected. Reproduces it with the smallest input and NarrativeTrace on, finds the first "
        "span where a value diverges and names it by its span id (the sequence diagram first "
        "when threads or tasks are involved), narrows to that span's sub-tree, fixes it there and "
        "checks the structural trace shows nothing else moved, pins the reproduction as a "
        "regression test and an approval baseline behind your yes, and reports the root cause by "
        "span id. Hands a defect in NarrativeTrace itself to narrativetrace-feedback. Say 'debug "
        "this with the trace', 'find where this value goes wrong', or 'why is this result wrong' "
        "to invoke it."
    ),
    when_to_use=(
        "Non-obvious triggers: a support ticket quoting a wrong amount or total; a rounding, "
        "currency or timezone difference between what was expected and what happened; a value "
        "that is right going into a service and wrong coming out; a flaky ordering between "
        "threads or tasks."
    ),
    fixture="examples/sixty_seconds",
    allowed_tools=(),
    steps=(
        _REPRODUCE,
        _SYMPTOM,
        _DIAGRAM,
        _LOCALIZE,
        _BISECT,
        _HAND_OFF,
        _FIX,
        _DELTA,
        _KEEP,
        *baseline_pin.STEPS,
        _REPORT,
    ),
    always=(
        CITE_SPAN_IDS,
        ReasonedRule(
            rule="Narrow to one span before reading its values.",
            reason=(
                "debugging is where values pay for themselves, but only on the span that "
                "diverged — a whole trace of values buries the one that matters"
            ),
        ),
        *baseline_pin.ALWAYS,
    ),
    never=(
        ReasonedRule(
            rule="Never change code before the diverging span is named.",
            reason=(
                "a fix made before the trace says where the value went wrong is a guess, and a "
                "guess that turns the test green hides the defect it missed"
            ),
        ),
        ReasonedRule(
            rule="Never make the symptom go away somewhere other than the diverging span.",
            reason=(
                "a correction downstream, a caught exception or a changed expectation silences "
                "the symptom and leaves the defect for the next caller of that span"
            ),
        ),
        NEVER_REDACTION_OFF,
        *baseline_pin.NEVER,
    ),
    sections=(FLAVOURS, SHAPES),
)
