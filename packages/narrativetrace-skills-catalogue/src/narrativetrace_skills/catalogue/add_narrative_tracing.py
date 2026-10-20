# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Getting a project from zero to a first trace, then to a real logger. Diagnosing an install that
is already wired up but not working is ``narrativetrace-doctor``'s job, not this skill's -- this
skill hands off to it, then ends by previewing the agent-skills install so the next session finds
them without being told about them (Phase 3 milestone 5, mirrors the Java reference's own last
step).

The install, from zero (B-87): the page ADDS the distribution the first-trace snippet imports --
``uv add narrativetrace`` -- and keeps ``uv sync``
as the CHECK that the lockfile it wrote reproduces. It used to say only ``uv sync --all-packages``
(a workspace sync that adds nothing, and fails outright in a directory with no ``pyproject.toml``)
because its replay ran in ``examples/sixty_seconds``, a workspace member where ``uv add`` would
rewrite this repository's own lockfile -- so the one project where a page that installs nothing
still passes was the only one it was proven in. The logging step imports only the standard
library, so no step adds a logger dependency. The Tier A2 replay therefore runs COLD: its fixture
(``evals/fixtures/empty-project``, a bare ``pyproject.toml`` with no dependency) copied outside
the repository, ``uv add`` resolving to this checkout's built wheels through a find-links source
(``tests/test_replay_cold_install.py``).

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
    SERVICE_IS_NAMED,
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

_FIXTURE = "packages/narrativetrace-skills-catalogue/evals/fixtures/empty-project"

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

FIRST_TRACE_HAS_TESTS = (
    "if the project already has tests — a test directory, a runner's table in its pyproject.toml "
    "or a test runner among its dependencies — and the doctor reports a test integration for "
    "that runner, do not add a demo script: run one existing test through that integration with "
    "output on, which writes that test's narrative files, .md and .nt, under the integration's "
    "output directory — the files narrativetrace-doctor, -verify, -debug and -explain read; "
    "print the rendered file so the trace is also on the console; the step is done when that "
    "test's files exist; a project whose runner has no integration keeps that runner and takes "
    "the console path below; "
)
"""Step 3's first branch (B-92): a project with tests gets its first trace from one of them, through
the test integration, so the files the other skills read exist. A runner with no integration is
never swapped for one that has it. Names no runner or framework."""

FIRST_TRACE_WRITES_NOTHING_WITHOUT_TESTS = (
    "; nothing is written to disk by this script — the application's log is the record once the "
    "logging bridge in the later step is wired; this page never adds a test runner or a test to "
    "a project that has none"
)
"""Appended to step 3's console branch (B-92): says plainly that the standalone script leaves no
file, and that the page does not create a test runner to get one."""

NAME_THE_SERVICE_DONE = (
    "the service has its own real name — set once, where the context is built or in the "
    "environment the service runs in (NARRATIVETRACE_SERVICE_NAME), never a placeholder; in an "
    "existing application the line that builds the context changes, no second context is added"
)
"""The service-name step's done-condition: the name is the project's own, not a copied example."""

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
            body=CommandStep(commands=("uv add narrativetrace", "uv sync")),
            verify=TOOLCHAIN_CHECKS_HOLD,
            failure=(
                FailureNote(
                    symptom=(
                        "the project is managed by pip, poetry or pdm rather than uv, or `uv add` "
                        "just wrote a uv.lock beside another manager's lockfile"
                    ),
                    cause=(
                        "this page spells its commands in uv, and the project uses another manager"
                    ),
                    fix=(
                        "remove the uv.lock uv wrote; a project on pip, poetry or pdm adds the "
                        "same distribution with its own command and checks with its own clean "
                        "install"
                    ),
                ),
                FailureNote(
                    symptom="`uv add` exits 2 with `No pyproject.toml found`",
                    cause=(
                        "the directory is no Python project yet, and `uv add` does not create one"
                    ),
                    fix="run `uv init --bare` once, then `uv add narrativetrace` again",
                ),
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
                FailureNote(
                    symptom=(
                        "a bare function, a lambda or a functools.partial gives no spans at all, "
                        "or a span carries the wrong class name"
                    ),
                    cause=(
                        "a span is named after type(target).__name__, and trace_object never "
                        "traces a function, lambda or partial"
                    ),
                    fix=(
                        "trace an instance of a class of your own, or pass "
                        'class_name="..." to trace_object to show a different name'
                    ),
                ),
                FailureNote(
                    symptom=(
                        "trace_object returns the object unwrapped and stderr says it cannot "
                        "trace it (excluded module ...)"
                    ),
                    cause=(
                        "the class is defined under a module prefix on the exclude list, whose "
                        "shipped default covers test and mocking libraries and APM runtimes"
                    ),
                    fix=(
                        "wrap a class of your own, or set NARRATIVETRACE_EXCLUDE (or the "
                        "exclude key) to the full list you want, which replaces the default"
                    ),
                ),
            ),
            condition=(
                FIRST_TRACE_HAS_TESTS
                + ENTRY_POINT_RUNS_ITSELF
                + FIRST_TRACE_WRITES_NOTHING_WITHOUT_TESTS
            ),
        ),
        SkillStep(
            title="Name the service",
            body=SnippetStep(
                path="examples/sixty_seconds/main_named_service.py", language="python"
            ),
            verify=SERVICE_IS_NAMED,
            done=NAME_THE_SERVICE_DONE,
            failure=(
                FailureNote(
                    symptom=("traces say unknown_service:python on the platform"),
                    cause="nobody named the service, so the fallback name is all there is",
                    fix=(
                        'pass service_identity=ServiceIdentity("orders") to the '
                        "ContextVarNarrativeContext, or set NARRATIVETRACE_SERVICE_NAME (and "
                        "NARRATIVETRACE_SERVICE_VERSION, NARRATIVETRACE_ENVIRONMENT) in the "
                        "environment the service runs in"
                    ),
                ),
            ),
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
                "Check the install with a clean `uv sync` after adding the package, rather than "
                "trusting whatever is already in the virtual environment."
            ),
            reason=(
                "`uv add` installs; the clean sync is the check that the lockfile it wrote "
                "reproduces -- a mismatched sibling version or a stale lockfile is the single "
                "most common install failure, and it only surfaces on a clean install"
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
