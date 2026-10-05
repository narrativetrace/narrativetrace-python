# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""D11: ``add-narrative-tracing``'s installer step may only ever PREVIEW ``narrativetrace init`` --
the applying form is the one thing this skill must never spell, because writing into ``AGENTS.md``
and ``.agents/skills/`` needs a person to read the diff first (mirrors the Java reference's own
``AddNarrativeTracingSkillTest``)."""

from __future__ import annotations

from narrativetrace_skills.catalogue.add_narrative_tracing import ADD_NARRATIVE_TRACING
from narrativetrace_skills.catalogue.installer_commands import (
    PREVIEW_INSTALL,
    VERIFY_PREVIEW_WROTE_NOTHING,
)
from narrativetrace_skills.skill import CommandStep, command_strings

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

    def test_skill_has_exactly_five_steps(self) -> None:
        """Ensures a step wasn't accidentally added or removed, which could go undetected if the
        last step's title check still passes."""
        assert len(ADD_NARRATIVE_TRACING.steps) == 5

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
        """The steps should flow logically: install, trace, logger, doctor, then installer preview.
        The order matters for skill usability."""
        titles = [step.title for step in ADD_NARRATIVE_TRACING.steps]
        assert titles[0] == "Install with the real toolchain"
        assert titles[1] == "First trace: wrap, call, render, run"
        assert titles[2] == "Send it to your logger"
        assert titles[3] == "Run the doctor and resolve its findings"
        assert titles[4] == "Install the skills for next time"
