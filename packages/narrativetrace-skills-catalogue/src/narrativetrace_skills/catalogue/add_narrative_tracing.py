# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Getting a project from zero to a first trace, then to a real logger. Diagnosing an install that
is already wired up but not working is ``narrativetrace-doctor``'s job, not this skill's -- this
skill hands off to it, then ends by previewing the agent-skills install so the next session finds
them without being told about them (Phase 3 milestone 5, mirrors the Java reference's own last
step).

Amendment (mirrors the TypeScript reference's own): the install step's ``verify`` must reinstall
clean, but the fixture (``examples/sixty_seconds``) is a workspace member with no ``pyproject.toml``
of its own -- ``uv add narrativetrace`` there would mutate this repo's own shared workspace
lockfile, an unacceptable side effect for a replay. The vocabulary-safe equivalent replayed here is
``uv sync --all-packages``; a real consumer's own ``uv add narrativetrace`` (shown in the rendered
step below, matching the docs' own quickstart) is unaffected -- this only changes what the SKILL's
own replay executes against ITS OWN fixture.

Right after the install, ONE step hands framework wiring to the doctor (Phase 6, D2 as amended):
run it, apply every ``config.<framework>-*`` fix in order. The page names no framework — the
installed doctor's own framework table is the oracle, so a release that adds a row reaches existing
projects through the doctor, never through a stale skill page.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue.doctor_commands import (
    DOCTOR_REPORT_WELL_FORMED,
    FRAMEWORK_FIXES_APPLIED,
    RUN_DOCTOR,
    TOOLCHAIN_CHECKS_HOLD,
)
from narrativetrace_skills.catalogue.installer_commands import (
    PREVIEW_INSTALL,
    VERIFY_PREVIEW_WROTE_NOTHING,
)
from narrativetrace_skills.skill import (
    CommandStep,
    FailureNote,
    ReasonedRule,
    Skill,
    SkillStep,
    SnippetStep,
)

_FIXTURE = "examples/sixty_seconds"

_HAS_AN_ENTRY_POINT = (
    "if the project already has an application entry point — a script or module that starts it, "
    "a web or application framework the doctor reports — "
)
"""The shared opening of both demo steps' conditions (Phase 6, D2). Names no framework: whether the
project already starts itself is read from its own layout and the doctor's report, never from a list
on this page."""

ENTRY_POINT_RUNS_ITSELF = (
    _HAS_AN_ENTRY_POINT
    + "do not create a demo main.py: run the application the way it already runs, exercise one "
    "real boundary, and read that request's trace; the verify below is for the standalone "
    "script, and in an existing application the step is done when that request's trace is in "
    "the output; otherwise create the smallest script as follows"
)
"""Step 3's condition: in a project that already starts itself the first trace is one real
boundary's, read from the application the way it already runs — never a demo script written over
the project's own entry point."""

ENTRY_POINT_KEEPS_ITS_LOGGING = (
    _HAS_AN_ENTRY_POINT
    + "do not create a second main.py or a second logging setup: add the filter and the "
    "export_to_logger call to the application's own logging configuration and the boundary you "
    "exercised; the verify below is for the standalone script, and in an existing application "
    "the step is done when that boundary's trace reaches the application's own logger; "
    "otherwise create the smallest script as follows"
)
"""Step 4's condition: the logging bridge is wired into the logging the application already has."""

ADD_NARRATIVE_TRACING = Skill(
    canonical_name="add-narrative-tracing",
    skill_class="mechanical",
    description=(
        "Installs NarrativeTrace into a Python project and gets it to a first trace. Use when "
        "NarrativeTrace is not yet installed, a project needs its very first traced call, or "
        "traces need to reach a real logger instead of bare print statements. Installs "
        "narrativetrace with uv add, wraps an object with trace_object, renders and runs the "
        "first trace, then wires the stdlib logging bridge so traces reach your logger. Applies "
        "the doctor's framework-wiring fixes for the frameworks the project already uses, and runs "
        "narrativetrace doctor to confirm the install is correctly wired -- narrativetrace-doctor "
        "owns diagnosis from there -- and previews the agent-skills install so the next session "
        "finds them. Say 'add narrative tracing to my "
        "service', 'install narrativetrace', 'get a trace in 60 seconds', 'wrap this object so "
        "I can see a trace', or 'send my traces to my logger' to invoke it."
    ),
    when_to_use=(
        "A project does not have NarrativeTrace yet, or has the package installed but has never "
        "produced a trace, or traces print to the console but nothing forwards them to a real "
        "logger."
    ),
    fixture=_FIXTURE,
    allowed_tools=("uv", "git"),
    steps=(
        SkillStep(
            title="Install with the real toolchain",
            body=CommandStep(commands=("uv sync --all-packages",)),
            verify=TOOLCHAIN_CHECKS_HOLD,
            failure=(
                FailureNote(
                    symptom="a sibling narrativetrace-* package disagrees on version",
                    cause=(
                        "an installed distribution outside the lockstep version the other "
                        "narrativetrace-* packages share"
                    ),
                    fix=(
                        "run the narrativetrace-doctor skill's toolchain.package-versions "
                        "check, then pin every narrativetrace-* dependency to the same version "
                        "and `uv sync`"
                    ),
                ),
            ),
        ),
        SkillStep(
            title="Wire the frameworks this project already uses",
            body=CommandStep(commands=(RUN_DOCTOR,)),
            verify=FRAMEWORK_FIXES_APPLIED,
            failure=(
                FailureNote(
                    symptom="a config.<framework>-* finding fails",
                    cause=(
                        "the doctor detected a framework this project uses whose NarrativeTrace "
                        "integration is not added, or is added but never wired"
                    ),
                    fix=(
                        "run the doctor; apply every config.<framework>-* fix it prints, in "
                        "order; a framework it reports as having no integration shipped is left "
                        "alone"
                    ),
                ),
            ),
        ),
        SkillStep(
            title="First trace: wrap, call, render, run",
            body=SnippetStep(path="examples/sixty_seconds/main.py", language="python"),
            verify="uv run python main.py",
            failure=(
                FailureNote(
                    symptom="a *args method's parameters render as one args: [...] value",
                    cause=(
                        "inspect.signature has nothing named to reconstruct per-argument that "
                        "Python itself does not have"
                    ),
                    fix='supply explicit names: @traced("first", "second", ...) above the method',
                ),
            ),
            condition=ENTRY_POINT_RUNS_ITSELF,
        ),
        SkillStep(
            title="Send it to your logger",
            body=SnippetStep(path="examples/sixty_seconds/main_with_logger.py", language="python"),
            verify="uv run python main_with_logger.py",
            condition=ENTRY_POINT_KEEPS_ITS_LOGGING,
        ),
        SkillStep(
            title="Run the doctor and resolve its findings",
            # The seam between the two skills: this step's own claim is "doctor ran and
            # produced a well-formed report to act on" -- resolving each finding is
            # narrativetrace-doctor's job.
            body=CommandStep(commands=(RUN_DOCTOR,)),
            verify=DOCTOR_REPORT_WELL_FORMED,
        ),
        SkillStep(
            title="Install the skills for next time",
            body=CommandStep(commands=(PREVIEW_INSTALL,)),
            # The install's hand-off to the next session (Phase 7, D7): once the skills are
            # installed, the session after this one reads what its changes did before reporting.
            done=(
                "the preview wrote nothing; the next session verifies with narrativetrace-verify "
                "— once a change's tests are green, it reads the trace before it reports"
            ),
            verify=VERIFY_PREVIEW_WROTE_NOTHING,
            failure=(
                FailureNote(
                    symptom="the command exits 1 with no carrier resolved",
                    cause=(
                        "no narrativetrace-skills distribution is installed and this project's "
                        "own narrativetrace bundles no reachable fallback"
                    ),
                    fix=(
                        "run `uv add narrativetrace-skills`, or point --from at a local carrier "
                        "directory or wheel"
                    ),
                ),
            ),
        ),
    ),
    always=(
        ReasonedRule(
            rule=(
                "Reinstall clean (`uv sync`) rather than trusting whatever is already in the "
                "virtual environment."
            ),
            reason=(
                "a mismatched sibling version or a stale lockfile is the single most common "
                "install failure, and it only surfaces on a clean install"
            ),
        ),
    ),
    never=(
        ReasonedRule(
            rule="Never assume a step worked without running its verify.",
            reason=(
                "self-reported success overstates reality -- a build claimed green that does "
                "not reproduce from clean is not evidence"
            ),
        ),
        ReasonedRule(
            rule="Never skip the final narrativetrace doctor call.",
            reason=(
                "it is the seam that catches anything these five steps did not -- "
                "narrativetrace-doctor owns diagnosis from here"
            ),
        ),
        ReasonedRule(
            rule="Never apply the installer without showing its diff first.",
            reason=(
                "it writes into AGENTS.md and the project's skill directories, and the approval "
                "for that is a person reading the diff -- run it with --dry-run, show the output, "
                "and let them run it again without the flag"
            ),
        ),
    ),
)
