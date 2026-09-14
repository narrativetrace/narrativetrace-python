# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Getting a project from zero to a first trace, then to a real logger. Diagnosing an install that
is already wired up but not working is ``narrativetrace-doctor``'s job, not this skill's -- this
skill's last step is handing off to it.

Amendment (mirrors the TypeScript reference's own): the install step's ``verify`` must reinstall
clean, but the fixture (``examples/sixty_seconds``) is a workspace member with no ``pyproject.toml``
of its own -- ``uv add narrativetrace`` there would mutate this repo's own shared workspace
lockfile, an unacceptable side effect for a replay. The vocabulary-safe equivalent replayed here is
``uv sync --all-packages``; a real consumer's own ``uv add narrativetrace`` (shown in the rendered
step below, matching the docs' own quickstart) is unaffected -- this only changes what the SKILL's
own replay executes against ITS OWN fixture.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue.doctor_commands import (
    DOCTOR_REPORT_WELL_FORMED,
    TOOLCHAIN_CHECKS_HOLD,
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

ADD_NARRATIVE_TRACING = Skill(
    canonical_name="add-narrative-tracing",
    skill_class="mechanical",
    description=(
        "Installs NarrativeTrace into a Python project and gets it to a first trace. Use when "
        "NarrativeTrace is not yet installed, a project needs its very first traced call, or "
        "traces need to reach a real logger instead of bare print statements. Installs "
        "narrativetrace with uv add, wraps an object with trace_object, renders and runs the "
        "first trace, then wires the stdlib logging bridge so traces reach your logger. Ends by "
        "running narrativetrace doctor to confirm the install is correctly wired -- "
        "narrativetrace-doctor owns diagnosis from there. Say 'add narrative tracing to my "
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
        ),
        SkillStep(
            title="Send it to your logger",
            body=SnippetStep(path="examples/sixty_seconds/main_with_logger.py", language="python"),
            verify="uv run python main_with_logger.py",
        ),
        SkillStep(
            title="Run the doctor and resolve its findings",
            # The seam between the two skills: this step's own claim is "doctor ran and
            # produced a well-formed report to act on" -- resolving each finding is
            # narrativetrace-doctor's job.
            body=CommandStep(commands=("uv run narrativetrace doctor || true",)),
            verify=DOCTOR_REPORT_WELL_FORMED,
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
                "it is the seam that catches anything these four steps did not -- "
                "narrativetrace-doctor owns diagnosis from here"
            ),
        ),
    ),
)
