# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adding NarrativeTrace Clarity -- the naming-clarity gate -- to a Python project, reading its
report, and renaming what it flags until the gate is clean. Mirrors the Java reference's
``add-narrativetrace-clarity``, adapted to this runtime's gate.

**@llmNote** Where the Java skill has a static scan AND a test-runner path (JUnit 5 extension, JUnit
4 rule), this runtime has ONE gate: the ``narrativetrace-clarity`` console script, which parses
Python SOURCE and scores each public class by its method and parameter names. There is no
test-runner reporter and no traced path, so the skill has no framework branch. Tracing itself being
broken is ``narrativetrace-doctor``'s job, which the description says.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue.clarity_commands import (
    GATE,
    GATE_RUNS,
    INSTALL_GATE,
    LIST_SOURCES,
    REPORTS_FRESH,
    RUN_TESTS,
    SCAN,
    SOURCES_TRACKED,
)
from narrativetrace_skills.skill import (
    CommandStep,
    FailureNote,
    ReasonedRule,
    Skill,
    SkillStep,
)

ADD_NARRATIVETRACE_CLARITY = Skill(
    canonical_name="add-narrativetrace-clarity",
    skill_class="guided",
    description=(
        "Adds or verifies NarrativeTrace Clarity in a Python project. Use when you want a first "
        "naming report, per-element suggestions, or an explicit clarity quality gate. Installs "
        "narrativetrace-clarity with uv add --dev, runs the real narrativetrace-clarity scan over "
        "the project's packages, checks the report is fresh and scored at least one class, renames "
        "what it flags, and re-runs until the gate is clean, preserving any thresholds the project "
        "already has. Route tracing itself being broken to narrativetrace-doctor. Say 'add a "
        "clarity report to this project', 'run narrativetrace-clarity', 'explain our clarity "
        "scores', 'make the clarity gate fail on low scores', or 'which names make this hard to "
        "read' to invoke it."
    ),
    when_to_use=(
        "A project has NarrativeTrace or needs a first clarity report, score explanation, or "
        "optional CI enforcement."
    ),
    fixture="examples/sixty_seconds",
    allowed_tools=("uv", "git"),
    steps=(
        SkillStep(
            title="Find what to scan and what is already there",
            body=CommandStep(commands=(LIST_SOURCES,)),
            verify=SOURCES_TRACKED,
            failure=(
                FailureNote(
                    symptom="the listing is empty",
                    cause="this is not a git checkout, or it tracks no Python",
                    fix=(
                        "run from the repository root; with no Python to read there is nothing "
                        "for clarity to score"
                    ),
                ),
            ),
        ),
        SkillStep(
            title="Install the gate as a development dependency",
            body=CommandStep(commands=(INSTALL_GATE,)),
            verify=GATE_RUNS,
            failure=(
                FailureNote(
                    symptom="the console script is not found",
                    cause="the dev dependency was added but the environment was not synced",
                    fix="run `uv sync`, then run the check again",
                ),
            ),
        ),
        SkillStep(
            title="Scan the packages and check the report is real",
            body=CommandStep(commands=(SCAN,)),
            verify=REPORTS_FRESH,
            failure=(
                FailureNote(
                    symptom="the scan prints `No classes found` and the check says no report",
                    cause=(
                        "the directory holds no public class: the scan scores classes, skips "
                        "names with a leading underscore, and does not score module-level "
                        "functions"
                    ),
                    fix="point it at the package directory that holds the project's classes",
                ),
                FailureNote(
                    symptom="the scores describe libraries, not the project",
                    cause=(
                        "the scan walked the project root and so the virtual environment under it"
                    ),
                    fix="pass the package directories, never `.`",
                ),
            ),
        ),
        SkillStep(
            title="Read the report and rename what it flags",
            body=CommandStep(commands=()),
            # No verify: judgmental -- whether a name now says what the code does is read, not
            # run. The re-run below is the mechanical check.
            failure=(
                FailureNote(
                    symptom="a flagged name is a domain word the project chose on purpose",
                    cause=(
                        "the scan scores against its built-in dictionaries unless a glossary is "
                        "committed"
                    ),
                    fix="leave the name and say why; the glossary rule below is the lasting fix",
                ),
                FailureNote(
                    symptom="a flagged method or parameter is part of a public API",
                    cause="renaming it breaks callers outside this repository",
                    fix="ask before renaming it, and keep the old name as a deprecated alias if so",
                ),
            ),
        ),
        SkillStep(
            title="Run the project's tests after the renames",
            body=CommandStep(commands=()),
            verify=RUN_TESTS,
            failure=(
                FailureNote(
                    symptom="a test fails with a name that no longer exists",
                    cause="a caller, a keyword argument or a string still uses the old name",
                    fix="search the whole repository for the old name and move every use",
                ),
            ),
        ),
        SkillStep(
            title="Re-run the gate until it is clean",
            body=CommandStep(commands=(GATE,)),
            verify=REPORTS_FRESH,
            failure=(
                FailureNote(
                    symptom=(
                        "exit 1 naming a class below --min-score, or HIGH issues over the limit"
                    ),
                    cause="a flagged name is still unclear, or a rename introduced another",
                    fix="read the new report, rename again, and repeat from the tests",
                ),
            ),
        ),
    ),
    always=(
        ReasonedRule(
            rule="Rename in snake_case, whatever case the suggestion's examples use.",
            reason=(
                "the suggestion text shares its wording with the other runtimes, so its examples "
                "are camelCase; the idea is the lesson, not the spelling"
            ),
        ),
        ReasonedRule(
            rule="Read both artefacts of every run, not only the exit code.",
            reason=("a scan that found no class exits 0 and leaves the last run's files in place"),
        ),
        ReasonedRule(
            rule="Use the thresholds the project already has, and ask before choosing new ones.",
            reason="enforcement is a decision the project makes, not a default the skill invents",
        ),
        ReasonedRule(
            rule=(
                "With no thresholds in the project and none requested, re-run the plain scan and "
                "report what is left."
            ),
            reason="a gate nobody asked for fails a build nobody expected to fail",
        ),
        ReasonedRule(
            rule=(
                "When the project commits a glossary and has narrativetrace-glossary, run the scan "
                "through `python -m narrativetrace_glossary.clarity_scan` with the same arguments."
            ),
            reason=(
                "that is the gate that reads the committed vocabulary, so a domain word the "
                "project chose on purpose is not flagged as unclear"
            ),
        ),
    ),
    never=(
        ReasonedRule(
            rule="Never lower or replace a threshold to hide a failure.",
            reason=(
                "a failing gate is evidence about the names; removing the evidence fixes nothing"
            ),
        ),
        ReasonedRule(
            rule="Never call a scan that found nothing a pass.",
            reason=(
                "an exit 0 with no scored class means the wrong directory was scanned, not that "
                "the names are clear"
            ),
        ),
        ReasonedRule(
            rule="Never add --warn-only to make the gate go green.",
            reason="an advisory gate exits 0 whatever it found, so green then proves nothing",
        ),
        ReasonedRule(
            rule="Never harvest a glossary only to read the existing vocabulary.",
            reason=(
                "the scan reads a committed glossary; creating one is a separate decision that "
                "writes to the project"
            ),
        ),
        ReasonedRule(
            rule="Never promise the score a rename will earn.",
            reason="a rename's score is measured by the next run, and the report may flag more",
        ),
    ),
)
