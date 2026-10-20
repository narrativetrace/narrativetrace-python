# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace-explain`` — explains what an application actually does by running one scenario
and reading its trace, for a user who has not thought of tracing at all. Mirrors Java's
``NarrativeTraceExplainSkill`` on this runtime's capture (the pytest plugin's ``narrative_trace``
fixture) and artifacts (``narrative-traces/``).

The other skills answer somebody who already wants tracing, is verifying a change, or is chasing a
symptom. This one answers "show me what my application actually does", "walk me through what
happens when a user checks out", "what does this endpoint call" — asked when nothing is broken and
no change needs reading, where the alternative is an agent reading source and describing what it
believes the code does.

Its first step is therefore a COST decision, not a run: a pure function, or a question ten lines of
source settle, is answered from the source with no install and no run, and the skill says so and
ends. :data:`FROM_THE_SOURCE` is that rule with its reason, and the negative Tier B case is what
proves it holds.

From there it is a reading loop, not a change loop: choose the one scenario that already exercises
the flow, install through ``add-narrative-tracing`` when the project has none, run that scenario,
read the value-free structural trace in its own order, open values only where the question needs
one, and explain the run by span id — marking every sentence that goes beyond the trace as an
inference, and naming the code no span covered. It fixes nothing: a defect the run exposes goes to
``narrativetrace-debug``, a change of this session's own to ``narrativetrace-verify``. It renders
the same :mod:`~narrativetrace_skills.catalogue.trace_reading` sections both of those do.

**@llmNote** No allowed tools, for the verify and debug skills' reason: the two skills this one
routes into write into the project (an install, a promotion), and a tool listed here would be
pre-approved for the turn that loads the page which routes — the turn before anybody has agreed to
anything. It promotes nothing itself, so
:func:`~narrativetrace_skills.lints.promotion_not_pre_approved` is vacuously green. In this
runtime a scenario is a pytest test whose collaborators are wrapped with ``trace_object`` and the
``narrative_trace`` fixture; a collaborator that is not wrapped has no span, which is why the last
step names the code no span covers.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue.explain_commands import RUN_THE_SCENARIO
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
)

FROM_THE_SOURCE = ReasonedRule(
    rule="Answer from the source when ten lines of source answer the question",
    reason=(
        "an install and a run cost the user time and tokens, and a trace of a pure function shows "
        "one call; the trace earns its keep where the path is not obvious — two collaborators "
        "over a boundary, a branch, a retry, state carried between calls"
    ),
)
"""The cost rule: the question the source answers is answered from the source."""

ONLY_WHAT_THE_QUESTION_NEEDS = (
    "only when the question is about a value that crossed a boundary, or about where the time "
    "went — the .nt carries neither; otherwise the shape is the whole answer"
)
"""Values and durations are opened only when the question is about one."""

_DECIDE = SkillStep(
    title="Decide whether the source already answers it, and say so",
    body=CommandStep(commands=()),
    done=(
        "before anything is installed or run, the reply says which it is: 'reading the source: "
        "<the reason>' when the question is about a pure function, one class with no "
        "collaborator, or a path ten lines of source settle — the answer is then that reading, "
        "with no install and no run, and the skill ends there; or 'tracing: <the reason>' when "
        "the flow crosses two or more collaborators over a boundary, branches, retries, runs "
        "async or concurrently, carries state between calls, or is code nobody in this session "
        "wrote. A whole flow's .nt is dozens of lines: cheap where the path is not obvious, "
        "waste where the source is already the answer"
    ),
)

_SCENARIO = SkillStep(
    title="Choose the one scenario that already exercises the flow",
    body=CommandStep(commands=()),
    done=(
        "the reply names ONE scenario — an existing test, or the entry point a reader would run "
        "— and which call of the flow asked about it drives; a scenario is written only where "
        "the project has none, and the reply says which of the two it is. Two scenarios is two "
        "traces to read where one answers the question"
    ),
)

_INSTALL = SkillStep(
    title="Install tracing first when the project has none",
    body=CommandStep(commands=()),
    condition=(
        "only when the project has no NarrativeTrace at all — no dependency on it in "
        "pyproject.toml and nothing under narrative-traces; where it is already installed, go "
        "straight to the run"
    ),
    done=(
        "add-narrative-tracing was followed to its own first trace and this skill resumed at the "
        "run below; nothing beyond that install was changed — an explanation does not refactor "
        "the code it is about"
    ),
)

_RUN = SkillStep(
    title="Run that one scenario with tracing on",
    body=CommandStep(commands=(RUN_THE_SCENARIO,)),
    condition=(
        "the project already has a test or entry point that exercises the flow — run that one, "
        "as it is; where none exists, add-narrative-tracing's own first-trace step is how one "
        "gets written, and it comes back here"
    ),
    done=(
        "the scenario ran and wrote a trace of its own: narrative-traces/structural holds an .nt "
        "for it, and narrative-traces/traces the .md beside it — a run that writes nothing is the "
        "failure below, never an answer; and the scenario ran as it was found, because a "
        "scenario edited to make the flow clearer is no longer the flow"
    ),
    failure=(
        FailureNote(
            symptom="the scenario runs but nothing appears under narrative-traces",
            cause=(
                "the test does not request the narrative_trace fixture, the collaborators on the "
                "flow are not wrapped with it, or the pytest plugin is not registered, so there "
                "is nothing to read"
            ),
            fix="run narrativetrace-doctor and apply its fix, then run the scenario again",
        ),
    ),
)

_SHAPE = SkillStep(
    title="Read the structural trace first, in the order it ran",
    body=CommandStep(commands=(LIST_STRUCTURAL,)),
    done=(
        "the .nt the scenario just wrote was opened and read whole before any value was looked "
        "at, and the reply walks it in its own order by span id (#1, #1.1, #1.2): which call ran "
        "under which, how many times, and which branch the run took — the flavours below say "
        "which file answers which question"
    ),
)

_VALUES = SkillStep(
    title="Open values only where the question needs one",
    body=CommandStep(commands=(LIST_NARRATIVES,)),
    condition=ONLY_WHAT_THE_QUESTION_NEEDS,
    done=(
        "only the spans the question needs were read in the .md narrative, found by the id the "
        ".nt gave them — not the whole file; a [REDACTED] value stays redacted and is reasoned "
        "about by its parameter name and the shape around it"
    ),
)

_HAND_OFF = SkillStep(
    title="Hand off when it stops being an explanation",
    body=CommandStep(commands=()),
    condition=(
        "only when the run shows something wrong — one of the shapes below, or a value that is "
        "not what the flow implies — or a change of this session's own is what the user is "
        "really asking about; otherwise go on to the explanation"
    ),
    done=(
        "narrativetrace-debug was started, with the span id of the first call that looks wrong, "
        "when the run showed a defect; or narrativetrace-verify when what needs reading is a "
        "change this session made. The explanation written so far goes with the hand-off, and "
        "this skill fixes nothing itself"
    ),
)

_EXPLAIN = SkillStep(
    title="Explain the run by span id, and mark what you inferred",
    body=CommandStep(commands=()),
    done=(
        "the explanation is in the user's own words and in the trace's own order: the calls the "
        "flow made, each claim citing the span id it rests on — a claim without an id is not a "
        "claim, and only ids in the .nt or .md read in this session count — the branch it took, "
        "and where the time went when that was the question. Every sentence that goes beyond "
        "what the trace shows is marked as an inference, and the last part names what was NOT "
        "observed: the code no span covers, because only wrapped or intercepted code has one, and "
        "the branches this run did not take"
    ),
)

NARRATIVETRACE_EXPLAIN = Skill(
    canonical_name="narrativetrace-explain",
    skill_class="guided",
    description=(
        "Use when someone asks what an application or a flow actually does, with nothing broken "
        "and no change needing verification: 'show me what my application actually does', "
        "'walk me through what happens when a user checks out', 'I inherited this service, how "
        "does an order flow', 'what does this endpoint call'. Load it BEFORE reading source "
        "files to describe them: it explains a Python application by running one scenario with "
        "NarrativeTrace on and reading the trace of what happened — evidence of the run, not a "
        "reading of the code. Decides first whether a trace is worth it: a question ten lines of "
        "source answer is answered from the source, with no install and no run. Otherwise it "
        "runs one existing test or entry point for that flow — installing through "
        "add-narrative-tracing when the project has none — reads the value-free structural "
        "trace, and explains the run by span id, marking what it inferred and naming the code "
        "no span covered. Hands a defect to narrativetrace-debug, a change to "
        "narrativetrace-verify."
    ),
    when_to_use=(
        "Non-obvious triggers: any request that would otherwise be answered by reading the "
        "source and describing it — an onboarding question about a service nobody in this "
        "session wrote, 'what does this endpoint call', a request to document or draw a flow "
        "before changing it, a question about where a request spends its time. Nothing has to "
        "be broken and no change has to be pending for this to be the right skill."
    ),
    fixture="examples/sixty_seconds",
    allowed_tools=(),
    steps=(_DECIDE, _SCENARIO, _INSTALL, _RUN, _SHAPE, _VALUES, _HAND_OFF, _EXPLAIN),
    always=(
        FROM_THE_SOURCE,
        CITE_SPAN_IDS,
        ReasonedRule(
            rule="Separate what the trace showed from what you inferred.",
            reason=(
                "a reader cannot check a claim that mixes the two, and the inference is exactly "
                "where an explanation is wrong while sounding most certain"
            ),
        ),
    ),
    never=(
        ReasonedRule(
            rule="Never present an unobserved call as something the trace showed.",
            reason=(
                "only wrapped or intercepted code has a span, so a call no span covers is an "
                "inference; naming it as observed is how an explanation becomes confidently "
                "wrong about the part nobody measured"
            ),
        ),
        ReasonedRule(
            rule="Never change the code in order to explain it.",
            reason=(
                "the user asked what the code does, not for a change — wrapping one more "
                "collaborator inside a scenario is reading, editing what runs in production is "
                "not"
            ),
        ),
        NEVER_REDACTION_OFF,
    ),
    sections=(FLAVOURS, SHAPES),
)
