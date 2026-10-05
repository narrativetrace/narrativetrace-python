# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Feature COMBINATIONS: a flag that changes one decision while another decision still refuses, two
skills where only one is somebody else's, a scope that silences half the plan while the other half
still has an opinion.

Each case here is an interaction no single-feature test exercises. Named after the Java port's
``AdversarialInitTest`` so the two lists diff — and that port's own note is worth repeating: two of
its generated cases asserted the OPPOSITE of what the code does, the code was right both times, and
the cases were rewritten to pin the real behaviour with the reason it is right. Both are below.
"""

from __future__ import annotations

from pathlib import Path

import carriers
import pytest

from narrativetrace_tooling.init import marked_block, provenance
from narrativetrace_tooling.init.action import (
    Action,
    AppendBlock,
    CreateFile,
    FileEdit,
    Refuse,
    ReplaceBlock,
)
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.init_planner import plan_init
from narrativetrace_tooling.init.options import InitOptions, Scope, Vendor
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence, ProjectState

AGENTS_MD = Path("AGENTS.md")
CLAUDE_MD = Path("CLAUDE.md")
CURSOR_RULES = Path(".cursorrules")
DOCTOR_DIRECTORY = Path(".agents/skills/doctor")
DOCTOR_PAGE = Path(".agents/skills/doctor/SKILL.md")
VENDOR_DOCTOR_PAGE = Path(".claude/skills/doctor/SKILL.md")

TWO_SECTIONS = (
    "<!-- narrativetrace:start -->\na\n<!-- narrativetrace:end -->\n"
    "<!-- narrativetrace:start -->\nb\n<!-- narrativetrace:end -->\n"
)


@pytest.fixture
def carrier(tmp_path: Path) -> Carrier:
    return carriers.fake(tmp_path, "doctor")


def action_on(plan: InitPlan, path: Path) -> Action | None:
    return next((action for action in plan.actions if action.path == path), None)


def after(plan: InitPlan, path: Path) -> str:
    found = action_on(plan, path)
    assert isinstance(found, FileEdit), f"no file edit on {path} in {plan.actions}"
    return found.after


def refusal_on(plan: InitPlan, path: Path) -> Refuse:
    found = action_on(plan, path)
    assert isinstance(found, Refuse), f"no refusal on {path} in {plan.actions}"
    return found


def foreign(name: str, flavour: SkillFlavour = SkillFlavour.AGENTS) -> InstalledSkill:
    return InstalledSkill(flavour, name, Presence.FOREIGN, body="theirs\n")


def ours(name: str, coordinate: str, body: str) -> InstalledSkill:
    return InstalledSkill(SkillFlavour.AGENTS, name, Presence.OURS, coordinate, body)


class TestScopeSilencesOneHalfAndTheOtherStillDecides:
    def test_scope_skills_leaves_both_context_files_alone_even_when_each_would_have_had_an_opinion(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(agents_md="# Agents\n", claude_md="# C\n", claude_directory=True)

        plan = plan_init(state, carrier, InitOptions(scope=Scope.SKILLS))

        assert action_on(plan, AGENTS_MD) is None
        assert action_on(plan, CLAUDE_MD) is None
        assert action_on(plan, DOCTOR_PAGE) is not None
        assert plan.has_refusals is False, "the refusals belonged to the half that was silenced"

    def test_scope_agents_md_covers_the_import_line_too_and_refuses_both_without_the_flag(
        self, carrier: Carrier
    ) -> None:
        """The import line is part of the ``AGENTS.md`` half: it points AT that file, so it travels
        with it."""
        state = ProjectState(agents_md="# Agents\n", claude_md="# C\n", claude_directory=True)

        plan = plan_init(state, carrier, InitOptions(scope=Scope.AGENTS_MD))

        assert isinstance(action_on(plan, AGENTS_MD), Refuse)
        assert isinstance(action_on(plan, CLAUDE_MD), Refuse)
        assert action_on(plan, DOCTOR_PAGE) is None
        assert plan.exit_code == 1


class TestOneFlagAnswersOneQuestionAndTheOthersStillStand:
    def test_force_overwrites_a_foreign_skill_while_the_vendor_context_file_is_still_refused(
        self, carrier: Carrier
    ) -> None:
        """``--force`` is about a skill directory somebody else owns. It says nothing about a
        context file, so the vendor file this project already has is still refused in the same plan
        — and the run exits 1 even though the forced half succeeded.

        This is one of the two cases whose generated version asserted the opposite. The code is
        right: a flag answers the question it is about and no other."""
        state = ProjectState(claude_md="# C\n", installed_skills=(foreign("doctor"),))

        plan = plan_init(state, carrier, InitOptions(force=True))

        assert isinstance(action_on(plan, DOCTOR_PAGE), ReplaceBlock)
        assert isinstance(action_on(plan, CLAUDE_MD), Refuse)
        assert plan.exit_code == 1

    def test_force_reaches_the_vendor_flavour_of_the_same_foreign_skill_too(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(
            claude_directory=True,
            installed_skills=(foreign("doctor"), foreign("doctor", SkillFlavour.CLAUDE)),
        )

        plan = plan_init(state, carrier, InitOptions(force=True))

        assert isinstance(action_on(plan, DOCTOR_PAGE), ReplaceBlock)
        assert isinstance(action_on(plan, VENDOR_DOCTOR_PAGE), ReplaceBlock)

    def test_refuses_one_skill_and_installs_the_other_in_the_same_plan(
        self, tmp_path: Path
    ) -> None:
        """One skill of ours, one somebody else's: the refusal is per skill, never per run."""
        two = carriers.fake(tmp_path / "two", "doctor", "clarity")
        state = ProjectState(installed_skills=(foreign("doctor"),))

        plan = plan_init(state, two, InitOptions())

        assert isinstance(action_on(plan, DOCTOR_DIRECTORY), Refuse)
        assert isinstance(action_on(plan, Path(".agents/skills/clarity/SKILL.md")), CreateFile)
        assert plan.exit_code == 1

    def test_a_vendor_choice_of_off_survives_every_other_flag(self, carrier: Carrier) -> None:
        state = ProjectState(claude_directory=True, claude_md="# C\n")
        everything_else = InitOptions(vendor_claude=Vendor.OFF, force=True, write_existing=True)

        plan = plan_init(state, carrier, everything_else)

        assert action_on(plan, VENDOR_DOCTOR_PAGE) is None
        assert action_on(plan, CLAUDE_MD) is not None, "the import line is not a vendor SKILL"


class TestWhatIsOursIsOurs:
    def test_rewrites_our_own_skill_page_when_it_has_drifted_from_the_carrier(
        self, carrier: Carrier
    ) -> None:
        """A skill of OURS whose page has drifted — hand-edited, or left by an older carrier — is
        rewritten without any flag. Ours is ours: the flag exists for directories that are not.

        The second case whose generated version asserted the opposite."""
        state = ProjectState(
            installed_skills=(ours("doctor", carriers.FAKE_COORDINATE, "hand edited\n"),)
        )

        plan = plan_init(state, carrier, InitOptions())

        assert isinstance(action_on(plan, DOCTOR_PAGE), ReplaceBlock)
        assert after(plan, DOCTOR_PAGE) == provenance.stamp(
            carriers.body("doctor", SkillFlavour.AGENTS), carriers.FAKE_COORDINATE
        )

    def test_an_upgrade_leaves_no_trace_of_the_carrier_it_replaced(self, carrier: Carrier) -> None:
        old = "narrativetrace-skills==0.0.1"
        state = ProjectState(
            installed_skills=(ours("doctor", old, provenance.stamp("---\nx\n---\nold\n", old)),)
        )

        content = after(plan_init(state, carrier, InitOptions()), DOCTOR_PAGE)

        assert provenance.coordinate_in(content) == carriers.FAKE_COORDINATE
        assert old not in content


class TestADryRunDecidesEverythingAndWritesNothing:
    def test_a_dry_run_still_refuses_what_a_real_run_would_refuse_and_still_exits_zero(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(agents_md="# Agents\n", claude_md="# C\n")

        plan = plan_init(state, carrier, InitOptions(dry_run=True))

        assert len(plan.refusals) == 2
        assert plan.exit_code == 0
        assert action_on(plan, DOCTOR_PAGE) is not None, "the rest of the plan is still decided"


class TestWhatAFilesShapeDoesToTheBlock:
    def test_appending_to_a_windows_file_leaves_no_unix_line_ending_behind(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(agents_md="# Agents\r\n")

        written = after(plan_init(state, carrier, InitOptions(write_existing=True)), AGENTS_MD)

        assert written.startswith("# Agents\r\n\r\n")
        assert "\n\n" not in written.replace("\r\n", "")
        assert "\r\n\r\n" in written

    def test_a_created_file_uses_unix_line_endings_because_there_is_no_file_to_follow(
        self, carrier: Carrier
    ) -> None:
        written = after(plan_init(ProjectState(), carrier, InitOptions()), AGENTS_MD)

        assert written.endswith("\n")
        assert "\r" not in written

    def test_only_a_created_file_carries_the_created_note(self, carrier: Carrier) -> None:
        """The created note marks a file the installer MADE — never one it merely wrote into."""
        created = plan_init(ProjectState(), carrier, InitOptions())
        appended = plan_init(ProjectState(agents_md=""), carrier, InitOptions(write_existing=True))

        assert isinstance(action_on(created, AGENTS_MD), CreateFile)
        assert marked_block.CREATED_NOTE in after(created, AGENTS_MD)
        assert isinstance(action_on(appended, AGENTS_MD), AppendBlock)
        assert marked_block.CREATED_NOTE not in after(appended, AGENTS_MD)
        assert not after(appended, AGENTS_MD).startswith("\n")

    def test_refuses_a_vendor_rule_file_with_two_sections_and_says_to_leave_one(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(marked_rule_files={".cursorrules": TWO_SECTIONS})

        reason = refusal_on(plan_init(state, carrier, InitOptions()), CURSOR_RULES).reason

        assert "leave exactly one" in reason
        assert "line 1" in reason
        assert "line 4" in reason


class TestCombinationsThisPortHasThatJavaDoesNot:
    def test_a_uv_project_and_a_vendor_directory_together_still_name_one_set_of_commands(
        self, carrier: Carrier
    ) -> None:
        """The two detected facts are independent: one decides the command spelling, the other
        decides whether the vendor flavour is installed. A plan carries both without either leaking
        into the other's decision."""
        state = ProjectState(uv_project=True, claude_directory=True)

        plan = plan_init(state, carrier, InitOptions())

        section = after(plan, AGENTS_MD)

        assert action_on(plan, VENDOR_DOCTOR_PAGE) is not None
        assert "`uv run narrativetrace doctor`" in section
        assert "`narrativetrace doctor`" not in section, (
            "every command carries the prefix or none do"
        )

    def test_the_output_directory_reaches_the_section_and_nothing_else(
        self, carrier: Carrier
    ) -> None:
        """A detected output directory is prose in one line of the section. It must not reach a
        skill page, which is carrier bytes plus one provenance line and nothing else."""
        state = ProjectState(output_directory="out/traces")

        plan = plan_init(state, carrier, InitOptions())

        assert "`out/traces`" in after(plan, AGENTS_MD)
        assert "out/traces" not in after(plan, DOCTOR_PAGE)
