# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""D11: ``add-narrative-tracing``'s installer step may only ever PREVIEW ``narrativetrace init`` --
the applying form is the one thing this skill must never spell, because writing into ``AGENTS.md``
and ``.agents/skills/`` needs a person to read the diff first (mirrors the Java reference's own
``AddNarrativeTracingSkillTest``)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from narrativetrace_skills.catalogue.add_narrative_tracing import ADD_NARRATIVE_TRACING
from narrativetrace_skills.catalogue.doctor_commands import FRAMEWORK_FIXES_APPLIED, RUN_DOCTOR
from narrativetrace_skills.catalogue.installer_commands import (
    PREVIEW_INSTALL,
    VERIFY_PREVIEW_WROTE_NOTHING,
)
from narrativetrace_skills.render.claude import render_claude_skill
from narrativetrace_skills.skill import CommandStep, command_strings

from narrativetrace_tooling.frameworks.table import rows_with_wiring_checks, wiring_check_ids

_APPLYING_FORM = "narrativetrace init"


class TestTheInstallerStepPreviewsOnly:
    def test_last_step_is_installing_the_skills(self) -> None:
        assert ADD_NARRATIVE_TRACING.steps[-1].title == "Install the skills for next time"

    def test_no_command_anywhere_in_the_skill_applies_the_installer(self) -> None:
        for command in command_strings(ADD_NARRATIVE_TRACING):
            if _APPLYING_FORM in command:
                assert "--dry-run" in command, command

    def test_no_verify_string_ever_invokes_init_without_dry_run(self) -> None:
        """``_APPLYING_FORM`` (a literal ``"narrativetrace init"`` substring) never actually
        appears in the verify script: it builds a subprocess argv list, so the two words sit in
        separate quoted list items (``"narrativetrace", "init"``), not side by side as text. Check
        for the two words separately instead, so a mutant that dropped ``--dry-run`` from that argv
        list is still caught -- a first version of this test asserted on ``_APPLYING_FORM`` the
        same way the command-string test above does and never once entered its own `if` branch."""
        for step in ADD_NARRATIVE_TRACING.steps:
            verify = step.verify
            if verify is not None and "narrativetrace" in verify and "init" in verify:
                assert "--dry-run" in verify, verify

    def test_the_regression_this_guards_against(self) -> None:
        """Proves the test above is not itself vacuous: the last step's real verify string does
        reach the checked branch (unlike a plain ``_APPLYING_FORM in verify`` substring check,
        which never matches it -- see the docstring above)."""
        verify = ADD_NARRATIVE_TRACING.steps[-1].verify
        assert verify is not None
        assert _APPLYING_FORM not in verify
        assert "narrativetrace" in verify
        assert "init" in verify

    def test_the_installer_step_itself_previews(self) -> None:
        step = ADD_NARRATIVE_TRACING.steps[-1]
        assert isinstance(step.body, CommandStep)
        assert step.body.commands == ("uv run narrativetrace init --dry-run",)

    def test_description_says_it_ends_by_previewing_the_skills_install(self) -> None:
        assert "previews the agent-skills install" in ADD_NARRATIVE_TRACING.description

    def test_never_rules_include_showing_the_diff_first(self) -> None:
        rules = [rule.rule for rule in ADD_NARRATIVE_TRACING.never]
        assert any("without showing its diff first" in rule for rule in rules)

    def test_skill_has_exactly_six_steps(self) -> None:
        """Ensures a step wasn't accidentally added or removed, which could go undetected if the
        last step's title check still passes."""
        assert len(ADD_NARRATIVE_TRACING.steps) == 6

    def test_preview_install_constant_is_exact_value(self) -> None:
        """PREVIEW_INSTALL is not tested for its literal value anywhere else; if someone changes
        it, only this catches it. It is used both by the skill and, embedded, by
        VERIFY_PREVIEW_WROTE_NOTHING to re-run the same command."""
        assert PREVIEW_INSTALL == "uv run narrativetrace init --dry-run"

    def test_verify_preview_writes_nothing_checks_all_required_conditions(self) -> None:
        """VERIFY_PREVIEW_WROTE_NOTHING's embedded script must check all three of the preview's
        definition of done: the command succeeded, the plan named both paths, and neither exists
        on disk afterward. Every literal here uses double quotes only (the module's own documented
        convention, since the whole script is wrapped in single quotes for the shell) -- a
        single-quoted variant appearing instead would itself be the regression this test exists to
        catch, not a spelling this test should also accept."""
        assert "returncode == 0" in VERIFY_PREVIEW_WROTE_NOTHING
        assert '"action(s)"' in VERIFY_PREVIEW_WROTE_NOTHING
        assert '".agents/skills"' in VERIFY_PREVIEW_WROTE_NOTHING
        assert '"AGENTS.md"' in VERIFY_PREVIEW_WROTE_NOTHING
        assert "exists()" in VERIFY_PREVIEW_WROTE_NOTHING

    def test_last_step_command_and_verify_are_compatible(self) -> None:
        """The last step runs a command and verifies with a string. Both should agree on what
        command is being run, so that the verify string actually checks what the command does."""
        step = ADD_NARRATIVE_TRACING.steps[-1]
        assert isinstance(step.body, CommandStep)
        command = step.body.commands[0]
        verify = step.verify
        assert verify is not None

        # Both should mention the same command parts
        assert "narrativetrace" in command and "narrativetrace" in verify
        assert "init" in command and "init" in verify
        assert "--dry-run" in command and "--dry-run" in verify

    def test_steps_are_in_logical_order(self) -> None:
        """The steps should flow logically: install, frameworks, trace, logger, doctor, then
        installer preview. The order matters for skill usability."""
        titles = [step.title for step in ADD_NARRATIVE_TRACING.steps]
        assert titles == [
            "Install with the real toolchain",
            "Wire the frameworks this project already uses",
            "First trace: wrap, call, render, run",
            "Send it to your logger",
            "Run the doctor and resolve its findings",
            "Install the skills for next time",
        ]


_REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "uv.lock").is_file())


def _rendered_page() -> str:
    return render_claude_skill(
        ADD_NARRATIVE_TRACING, lambda path: (_REPO_ROOT / path).read_text(encoding="utf-8")
    )


class TestTheFrameworkStepHandsWiringToTheDoctor:
    """Phase 6, D2 as amended: right after the install, ONE step hands framework wiring to the
    doctor — run it, apply every ``config.<framework>-*`` fix it prints, in order; a framework it
    reports as having no integration shipped is left alone. The installed doctor's own framework
    table is the oracle, so the page never goes stale when a release adds a row."""

    def test_it_is_the_step_right_after_the_install(self) -> None:
        titles = [step.title for step in ADD_NARRATIVE_TRACING.steps]
        assert titles[:2] == [
            "Install with the real toolchain",
            "Wire the frameworks this project already uses",
        ]

    def test_it_runs_the_doctor_and_verifies_against_the_installed_table(self) -> None:
        step = ADD_NARRATIVE_TRACING.steps[1]
        assert step.body == CommandStep(commands=(RUN_DOCTOR,))
        assert step.verify == FRAMEWORK_FIXES_APPLIED
        assert "from narrativetrace_tooling.frameworks.table import wiring_check_ids" in (
            FRAMEWORK_FIXES_APPLIED
        )

    def test_its_failure_note_is_the_cross_port_wording(self) -> None:
        (note,) = ADD_NARRATIVE_TRACING.steps[1].failure
        assert note.symptom == "a config.<framework>-* finding fails"
        assert note.fix == (
            "run the doctor; apply every config.<framework>-* fix it prints, in order; a "
            "framework it reports as having no integration shipped is left alone"
        )

    def test_the_rendered_page_names_no_framework_the_doctor_checks(self) -> None:
        """Every row the doctor checks, by name and by marker distribution. The default-logger row
        is the core's own logging bridge — this skill's "Send it to your logger" step — not a
        framework the doctor wires."""
        page = _rendered_page().lower()
        for row in rows_with_wiring_checks():
            for word in (row.name, *row.marker.distributions):
                assert re.search(rf"(?<![\w-]){re.escape(word.lower())}(?![\w-])", page) is None, (
                    f"{row.id}: the page names {word!r}"
                )

    def test_the_verify_holds_every_framework_finding_to_a_pass(self) -> None:
        """Run the verify's own script against reports: one failing framework finding fails it,
        every framework finding passing (core findings failing) passes it."""
        script = FRAMEWORK_FIXES_APPLIED.split("uv run python -c '", 1)[1].rstrip("'")
        findings = [{"id": i, "status": "pass", "fix": ""} for i in wiring_check_ids()]
        core_fail = [{"id": "trap.redaction-proof", "status": "fail", "fix": "x"}]

        assert _run(script, {"findings": findings + core_fail}).returncode == 0
        findings[1] = {"id": findings[1]["id"], "status": "fail", "fix": "add the lines"}
        failed = _run(script, {"findings": findings})
        assert failed.returncode == 1
        assert failed.stdout == f"{findings[1]['id']}: add the lines\n"


class TestAnExistingEntryPointIsKept:
    """Phase 6, D2: the demo steps write a ``main.py``-shaped script. In a project that already
    starts itself that script is a second entry point at best and an overwrite of the project's own
    at worst, so those two steps are conditional — run the application as it runs, exercise one
    real boundary, read that request's trace. The condition names no framework."""

    _DEMO_STEPS = ("First trace: wrap, call, render, run", "Send it to your logger")

    def _conditions(self) -> dict[str, str | None]:
        return {step.title: step.condition for step in ADD_NARRATIVE_TRACING.steps}

    def test_exactly_the_two_demo_steps_are_conditional(self) -> None:
        conditional = {title for title, when in self._conditions().items() if when is not None}
        assert conditional == set(self._DEMO_STEPS)

    def test_the_first_trace_step_says_to_run_the_application_as_it_runs(self) -> None:
        assert self._conditions()["First trace: wrap, call, render, run"] == (
            "if the project already has an application entry point — a script or module that "
            "starts it, a web or application framework the doctor reports — do not create a "
            "demo main.py: run the application the way it already runs, exercise one real "
            "boundary, and read that request's trace; the verify below is for the standalone "
            "script, and in an existing application the step is done when that request's trace "
            "is in the output; otherwise create the smallest script as follows"
        )

    def test_the_logger_step_adds_to_the_applications_own_logging(self) -> None:
        assert self._conditions()["Send it to your logger"] == (
            "if the project already has an application entry point — a script or module that "
            "starts it, a web or application framework the doctor reports — do not create a "
            "second main.py or a second logging setup: add the filter and the export_to_logger "
            "call to the application's own logging configuration and the boundary you "
            "exercised; the verify below is for the standalone script, and in an existing "
            "application the step is done when that boundary's trace reaches the application's "
            "own logger; otherwise create the smallest script as follows"
        )

    def test_the_rendered_page_puts_each_when_line_between_heading_and_snippet(self) -> None:
        page = _rendered_page()
        for title, index in zip(self._DEMO_STEPS, (3, 4), strict=True):
            when = self._conditions()[title]
            assert f"## {index}. {title}\n\n**when:** {when}\n\n<!-- snippet: " in page

    def test_no_other_step_renders_a_when_line(self) -> None:
        assert _rendered_page().count("**when:**") == 2


def _run(script: str, report: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - this interpreter, the catalogue's own verify script
        [sys.executable, "-c", script],
        input=json.dumps(report),
        capture_output=True,
        text=True,
        check=False,
    )


class TestHandsOffToVerify:
    """Phase 7 D7: the install's last step tells the next session how it will verify."""

    def test_the_last_step_names_narrativetrace_verify_as_the_next_sessions_check(self) -> None:
        last = ADD_NARRATIVE_TRACING.steps[-1]
        assert last.done == (
            "the preview wrote nothing; the next session verifies with narrativetrace-verify — "
            "once a change's tests are green, it reads the trace before it reports"
        )
