# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Every row of the existing-file policy, one case each, plus the near misses that decide whether a
row applies at all. The planner is pure, so none of this touches a disk: a snapshot is built by hand
and the plan is read back.

Named after the Java port's ``InitPlannerTest`` so the two lists diff.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import carriers
import pytest

from narrativetrace_tooling.init import marked_block, provenance
from narrativetrace_tooling.init.action import (
    Action,
    AppendBlock,
    AppendLine,
    CreateFile,
    FileEdit,
    Refuse,
    ReplaceBlock,
)
from narrativetrace_tooling.init.agents_md_block import render_agents_md_block
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.init_planner import plan_init
from narrativetrace_tooling.init.options import InitOptions, Scope, Vendor
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence, ProjectState

AGENTS_MD = Path("AGENTS.md")
CLAUDE_MD = Path("CLAUDE.md")
DOCTOR_DIRECTORY = Path(".agents/skills/doctor")
DOCTOR_PAGE = Path(".agents/skills/doctor/SKILL.md")
VENDOR_DOCTOR_PAGE = Path(".claude/skills/doctor/SKILL.md")
CURSOR_RULES = Path(".cursorrules")

MISSING: Any = None

TWO_SECTIONS = (
    "<!-- narrativetrace:start -->\na\n<!-- narrativetrace:end -->\n"
    "<!-- narrativetrace:start -->\nb\n<!-- narrativetrace:end -->\n"
)

BOM = "﻿"


@pytest.fixture
def carrier(tmp_path: Path) -> Carrier:
    return carriers.fake(tmp_path, "doctor")


def write_existing() -> InitOptions:
    return dataclasses.replace(InitOptions(), write_existing=True)


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


def ours(name: str, coordinate: str, body: str) -> InstalledSkill:
    return InstalledSkill(SkillFlavour.AGENTS, name, Presence.OURS, coordinate, body)


def foreign(name: str, body: str = "theirs\n") -> InstalledSkill:
    return InstalledSkill(SkillFlavour.AGENTS, name, Presence.FOREIGN, body=body)


class TestTheManagedHome:
    def test_creates_agents_md_with_the_block_and_the_created_note_when_there_is_none(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState()

        plan = plan_init(state, carrier, InitOptions())

        assert isinstance(action_on(plan, AGENTS_MD), CreateFile)
        assert after(plan, AGENTS_MD) == (
            "<!-- narrativetrace:created -->\n" + render_agents_md_block(carrier, state)
        )

    def test_refuses_an_existing_agents_md_without_the_flag_and_names_the_flag(
        self, carrier: Carrier
    ) -> None:
        plan = plan_init(ProjectState(agents_md="# Agents\n"), carrier, InitOptions())

        assert "--write-existing" in refusal_on(plan, AGENTS_MD).reason
        assert plan.exit_code == 1

    def test_appends_to_an_existing_agents_md_with_the_flag(self, carrier: Carrier) -> None:
        state = ProjectState(agents_md="# Agents\n")

        plan = plan_init(state, carrier, write_existing())

        assert isinstance(action_on(plan, AGENTS_MD), AppendBlock)
        assert after(plan, AGENTS_MD) == "# Agents\n\n" + render_agents_md_block(carrier, state)

    def test_replaces_our_own_block_without_any_flag(self, carrier: Carrier) -> None:
        old = (
            "# Agents\n\n<!-- narrativetrace:start narrativetrace-skills==0.0.1 -->\n"
            "stale\n<!-- narrativetrace:end -->\n\ntail\n"
        )
        state = ProjectState(agents_md=old)

        plan = plan_init(state, carrier, InitOptions())

        assert isinstance(action_on(plan, AGENTS_MD), ReplaceBlock)
        assert after(plan, AGENTS_MD) == (
            "# Agents\n\n" + render_agents_md_block(carrier, state) + "\ntail\n"
        )

    def test_plans_nothing_for_an_agents_md_that_is_already_current(self, carrier: Carrier) -> None:
        written = "<!-- narrativetrace:created -->\n" + render_agents_md_block(
            carrier, ProjectState()
        )
        state = ProjectState(agents_md=written)

        assert action_on(plan_init(state, carrier, InitOptions()), AGENTS_MD) is None

    def test_refuses_an_agents_md_with_two_blocks_and_names_the_lines(
        self, carrier: Carrier
    ) -> None:
        plan = plan_init(ProjectState(agents_md=TWO_SECTIONS), carrier, write_existing())

        reason = refusal_on(plan, AGENTS_MD).reason
        assert "line 1" in reason
        assert "line 4" in reason
        assert "leave exactly one" in reason

    def test_refuses_an_agents_md_with_a_marker_that_never_closes(self, carrier: Carrier) -> None:
        state = ProjectState(agents_md="<!-- narrativetrace:start -->\nbody\n")

        plan = plan_init(state, carrier, write_existing())

        assert "line 1" in refusal_on(plan, AGENTS_MD).reason

    def test_the_rest_of_the_plan_proceeds_when_agents_md_is_refused(
        self, carrier: Carrier
    ) -> None:
        plan = plan_init(ProjectState(agents_md=TWO_SECTIONS), carrier, InitOptions())

        assert isinstance(action_on(plan, DOCTOR_PAGE), CreateFile)
        assert plan.has_refusals is True

    def test_does_not_mistake_a_marker_inside_a_fenced_block_for_ours(
        self, carrier: Carrier
    ) -> None:
        documented = (
            "# Agents\n\n```\n<!-- narrativetrace:start -->\n<!-- narrativetrace:end -->\n```\n"
        )
        state = ProjectState(agents_md=documented)

        plan = plan_init(state, carrier, write_existing())

        assert isinstance(action_on(plan, AGENTS_MD), AppendBlock)
        assert after(plan, AGENTS_MD) == documented + "\n" + render_agents_md_block(carrier, state)

    def test_writes_the_block_with_the_files_own_line_endings(self, carrier: Carrier) -> None:
        state = ProjectState(agents_md="# Agents\r\n")

        written = after(plan_init(state, carrier, write_existing()), AGENTS_MD)

        assert written == "# Agents\r\n\r\n" + marked_block.with_eol(
            render_agents_md_block(carrier, state), "\r\n"
        )
        assert "\r\r" not in written

    def test_keeps_a_byte_order_mark_and_a_missing_final_newline_in_mind(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(agents_md=BOM + "# Agents")

        written = after(plan_init(state, carrier, write_existing()), AGENTS_MD)

        assert written == BOM + "# Agents\n\n" + render_agents_md_block(carrier, state)

    def test_appends_to_an_empty_but_existing_agents_md_with_the_flag(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(agents_md="")

        plan = plan_init(state, carrier, write_existing())

        assert isinstance(action_on(plan, AGENTS_MD), AppendBlock)
        assert after(plan, AGENTS_MD) == render_agents_md_block(carrier, state)


class TestAnUnfinishedFence:
    """Found by the generative round trip, not by review: a block appended after an unfinished fence
    lands INSIDE it, where the next run's scan cannot see its own markers — so the run after that
    appends a second copy, and so on. Refusing is the only safe answer; closing somebody's fence for
    them is not."""

    def test_refuses_to_append_to_an_agents_md_that_ends_inside_an_unfinished_fence(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(agents_md="# Agents\n\n```\nnot closed\n")

        plan = plan_init(state, carrier, write_existing())

        assert "unfinished fenced code block" in refusal_on(plan, AGENTS_MD).reason

    def test_refuses_to_add_the_import_line_to_a_vendor_file_ending_inside_one(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(claude_md="# Project\n\n~~~\nnot closed\n")

        plan = plan_init(state, carrier, write_existing())

        assert "unfinished fenced code block" in refusal_on(plan, CLAUDE_MD).reason

    def test_still_replaces_our_own_section_in_a_file_whose_fence_opens_after_it(
        self, carrier: Carrier
    ) -> None:
        text = (
            "<!-- narrativetrace:start -->\nstale\n<!-- narrativetrace:end -->\n\n```\nnot closed\n"
        )

        plan = plan_init(ProjectState(agents_md=text), carrier, InitOptions())

        assert isinstance(action_on(plan, AGENTS_MD), ReplaceBlock)


class TestTheVendorContextFile:
    def test_creates_no_vendor_context_file_when_the_project_has_none(
        self, carrier: Carrier
    ) -> None:
        assert action_on(plan_init(ProjectState(), carrier, InitOptions()), CLAUDE_MD) is None

    def test_appends_the_import_line_to_an_existing_vendor_context_file_with_the_flag(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(claude_md="# Project\n")

        plan = plan_init(state, carrier, write_existing())

        assert isinstance(action_on(plan, CLAUDE_MD), AppendLine)
        assert after(plan, CLAUDE_MD) == "# Project\n\n@AGENTS.md\n"

    def test_refuses_to_touch_the_vendor_context_file_without_the_flag(
        self, carrier: Carrier
    ) -> None:
        plan = plan_init(ProjectState(claude_md="# Project\n"), carrier, InitOptions())

        assert "--write-existing" in refusal_on(plan, CLAUDE_MD).reason

    def test_leaves_a_vendor_context_file_that_already_imports_alone(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(claude_md="# Project\n\n@AGENTS.md\n")

        assert action_on(plan_init(state, carrier, write_existing()), CLAUDE_MD) is None

    def test_counts_an_import_line_with_trailing_spaces_as_already_there(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(claude_md="# Project\n\n@AGENTS.md   \n")

        assert action_on(plan_init(state, carrier, write_existing()), CLAUDE_MD) is None

    def test_does_not_count_an_import_line_inside_a_comment_or_a_fence(
        self, carrier: Carrier
    ) -> None:
        commented = ProjectState(claude_md="<!-- @AGENTS.md -->\n")
        fenced = ProjectState(claude_md="```\n@AGENTS.md\n```\n")

        assert isinstance(
            action_on(plan_init(commented, carrier, write_existing()), CLAUDE_MD), AppendLine
        )
        assert isinstance(
            action_on(plan_init(fenced, carrier, write_existing()), CLAUDE_MD), AppendLine
        )


class TestTheSkills:
    def test_copies_every_skill_into_the_open_standard_path_with_its_provenance_line(
        self, carrier: Carrier
    ) -> None:
        plan = plan_init(ProjectState(), carrier, InitOptions())

        assert after(plan, DOCTOR_PAGE) == provenance.stamp(
            carriers.body("doctor", SkillFlavour.AGENTS), carriers.FAKE_COORDINATE
        )
        assert provenance.coordinate_in(after(plan, DOCTOR_PAGE)) == carriers.FAKE_COORDINATE

    def test_installs_the_vendor_flavour_where_the_vendor_is_detected(
        self, carrier: Carrier
    ) -> None:
        by_directory = plan_init(ProjectState(claude_directory=True), carrier, InitOptions())
        by_context_file = plan_init(ProjectState(claude_md="# C\n"), carrier, write_existing())
        by_neither = plan_init(ProjectState(), carrier, InitOptions())

        assert action_on(by_directory, VENDOR_DOCTOR_PAGE) is not None
        assert action_on(by_context_file, VENDOR_DOCTOR_PAGE) is not None
        assert action_on(by_neither, VENDOR_DOCTOR_PAGE) is None

    def test_obeys_an_explicit_vendor_choice_over_detection(self, carrier: Carrier) -> None:
        on = dataclasses.replace(InitOptions(), vendor_claude=Vendor.ON)
        off = dataclasses.replace(InitOptions(), vendor_claude=Vendor.OFF)

        forced_on = plan_init(ProjectState(), carrier, on)
        forced_off = plan_init(ProjectState(claude_directory=True), carrier, off)

        assert action_on(forced_on, VENDOR_DOCTOR_PAGE) is not None
        assert action_on(forced_off, VENDOR_DOCTOR_PAGE) is None

    def test_plans_nothing_for_a_skill_that_is_already_exactly_right(
        self, carrier: Carrier
    ) -> None:
        installed = provenance.stamp(
            carriers.body("doctor", SkillFlavour.AGENTS), carriers.FAKE_COORDINATE
        )
        state = ProjectState(
            installed_skills=(ours("doctor", carriers.FAKE_COORDINATE, installed),)
        )

        assert action_on(plan_init(state, carrier, InitOptions()), DOCTOR_PAGE) is None

    def test_upgrades_a_skill_installed_from_an_older_carrier_without_any_flag(
        self, carrier: Carrier
    ) -> None:
        old = "narrativetrace-skills==0.0.1"
        older = provenance.stamp("---\nname: doctor\n---\nold\n", old)
        state = ProjectState(installed_skills=(ours("doctor", old, older),))

        plan = plan_init(state, carrier, InitOptions())

        assert isinstance(action_on(plan, DOCTOR_PAGE), ReplaceBlock)
        assert provenance.coordinate_in(after(plan, DOCTOR_PAGE)) == carriers.FAKE_COORDINATE

    def test_refuses_a_skill_directory_somebody_else_owns_and_lets_the_others_proceed(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(installed_skills=(foreign("doctor"),))

        plan = plan_init(state, carrier, InitOptions())

        assert "--force" in refusal_on(plan, DOCTOR_DIRECTORY).reason
        assert action_on(plan, AGENTS_MD) is not None

    def test_overwrites_a_foreign_skill_directory_when_forced(self, carrier: Carrier) -> None:
        state = ProjectState(installed_skills=(foreign("doctor"),))

        plan = plan_init(state, carrier, dataclasses.replace(InitOptions(), force=True))

        assert isinstance(action_on(plan, DOCTOR_PAGE), ReplaceBlock)

    def test_creates_the_page_when_a_foreign_directory_has_none_and_force_is_given(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(installed_skills=(foreign("doctor", body=""),))

        plan = plan_init(state, carrier, dataclasses.replace(InitOptions(), force=True))

        assert isinstance(action_on(plan, DOCTOR_PAGE), CreateFile)

    def test_refuses_a_file_sitting_where_a_skill_directory_belongs_even_when_forced(
        self, carrier: Carrier
    ) -> None:
        """``--force`` covers foreign CONTENT, never structure."""
        state = ProjectState(
            installed_skills=(
                InstalledSkill(SkillFlavour.AGENTS, "doctor", Presence.NOT_A_DIRECTORY),
            )
        )

        plan = plan_init(state, carrier, dataclasses.replace(InitOptions(), force=True))

        assert "not a directory" in refusal_on(plan, DOCTOR_DIRECTORY).reason


class TestTheRefusalsWordForWord:
    """Each refusal in full, not by fragment.

    A refusal is the one output of this planner a person acts on: it has to say what was refused and
    what to pass. Asserting a fragment leaves every rewording of the rest invisible, so the exact
    sentence is the assertion — the same reason the section's own text is asserted word for word.
    """

    def test_a_skill_directory_somebody_else_owns(self, carrier: Carrier) -> None:
        state = ProjectState(installed_skills=(foreign("doctor"),))

        plan = plan_init(state, carrier, InitOptions())

        assert refusal_on(plan, DOCTOR_DIRECTORY).reason == (
            ".agents/skills/doctor was not installed by narrativetrace — re-run with --force to"
            " overwrite this skill, or move the directory aside"
        )

    def test_a_file_where_a_skill_directory_belongs(self, carrier: Carrier) -> None:
        state = ProjectState(
            installed_skills=(
                InstalledSkill(SkillFlavour.AGENTS, "doctor", Presence.NOT_A_DIRECTORY),
            )
        )

        plan = plan_init(state, carrier, InitOptions())

        assert refusal_on(plan, DOCTOR_DIRECTORY).reason == (
            ".agents/skills/doctor is not a directory — move it aside and run the install again"
        )

    def test_a_context_file_that_exists_and_carries_no_section(self, carrier: Carrier) -> None:
        plan = plan_init(ProjectState(agents_md="# Agents\n"), carrier, InitOptions())

        assert refusal_on(plan, AGENTS_MD).reason == (
            "AGENTS.md exists and carries no NarrativeTrace section — re-run with --write-existing"
            " to append one"
        )

    def test_a_context_file_with_two_sections(self, carrier: Carrier) -> None:
        plan = plan_init(ProjectState(agents_md=TWO_SECTIONS), carrier, InitOptions())

        assert refusal_on(plan, AGENTS_MD).reason == (
            "AGENTS.md carries two or more NarrativeTrace sections (line 1, line 4) — leave exactly"
            " one"
        )

    def test_a_context_file_whose_markers_do_not_pair_up(self, carrier: Carrier) -> None:
        state = ProjectState(agents_md="<!-- narrativetrace:start -->\nbody\n")

        plan = plan_init(state, carrier, InitOptions())

        assert refusal_on(plan, AGENTS_MD).reason == (
            "AGENTS.md: line 1: a narrativetrace:start marker with no end below it"
        )

    def test_a_context_file_that_ends_inside_an_unfinished_fence(self, carrier: Carrier) -> None:
        state = ProjectState(agents_md="# Agents\n\n```\nnot closed\n")

        plan = plan_init(state, carrier, write_existing())

        assert refusal_on(plan, AGENTS_MD).reason == (
            "AGENTS.md ends inside an unfinished fenced code block — close the fence, and anything"
            " appended after it will be read as text rather than as code"
        )

    def test_a_vendor_context_file_that_does_not_import_the_managed_home(
        self, carrier: Carrier
    ) -> None:
        plan = plan_init(ProjectState(claude_md="# Project\n"), carrier, InitOptions())

        assert refusal_on(plan, CLAUDE_MD).reason == (
            "CLAUDE.md exists and does not import AGENTS.md — re-run with --write-existing to add"
            " the one-line import"
        )


class TestScopeRuleFilesAndThePlanItself:
    def test_plans_only_the_half_it_was_asked_for(self, carrier: Carrier) -> None:
        state = ProjectState()

        skills_only = plan_init(
            state, carrier, dataclasses.replace(InitOptions(), scope=Scope.SKILLS)
        )
        section_only = plan_init(
            state, carrier, dataclasses.replace(InitOptions(), scope=Scope.AGENTS_MD)
        )

        assert action_on(skills_only, DOCTOR_PAGE) is not None
        assert action_on(skills_only, AGENTS_MD) is None
        assert action_on(section_only, DOCTOR_PAGE) is None
        assert action_on(section_only, AGENTS_MD) is not None

    def test_keeps_an_existing_block_in_a_vendor_rule_file_up_to_date(
        self, carrier: Carrier
    ) -> None:
        rules = "# rules\n\n<!-- narrativetrace:start -->\nstale\n<!-- narrativetrace:end -->\n"
        state = ProjectState(marked_rule_files={".cursorrules": rules})

        plan = plan_init(state, carrier, InitOptions())

        assert isinstance(action_on(plan, CURSOR_RULES), ReplaceBlock)
        assert render_agents_md_block(carrier, state) in after(plan, CURSOR_RULES)

    def test_refuses_a_vendor_rule_file_with_two_blocks(self, carrier: Carrier) -> None:
        state = ProjectState(marked_rule_files={".cursorrules": TWO_SECTIONS})

        plan = plan_init(state, carrier, InitOptions())

        assert isinstance(action_on(plan, CURSOR_RULES), Refuse)

    def test_never_appends_a_section_to_a_rule_file_that_carries_none(
        self, carrier: Carrier
    ) -> None:
        """A vendor rule file is never created and never appended to, whatever flags were given: an
        existing managed section in one is kept current, and that is all."""
        state = ProjectState(marked_rule_files={".cursorrules": "# rules\n"})

        plan = plan_init(state, carrier, write_existing())

        assert "--write-existing" in refusal_on(plan, CURSOR_RULES).reason

    def test_stamps_the_plan_with_the_carrier_and_carries_the_dry_run_flag(
        self, carrier: Carrier
    ) -> None:
        plan = plan_init(ProjectState(), carrier, dataclasses.replace(InitOptions(), dry_run=True))

        assert plan.carrier == carriers.FAKE_COORDINATE
        assert plan.dry_run is True
        assert plan.exit_code == 0

    def test_never_plans_two_actions_on_one_path(self, carrier: Carrier) -> None:
        state = ProjectState(
            claude_directory=True,
            claude_md="# C\n",
            agents_md="# A\n",
            marked_rule_files={
                ".cursorrules": "<!-- narrativetrace:start -->\n<!-- narrativetrace:end -->\n"
            },
        )

        paths = [action.path for action in plan_init(state, carrier, write_existing()).actions]

        assert len(set(paths)) == len(paths)

    def test_refuses_to_plan_without_a_snapshot_a_carrier_or_options(
        self, carrier: Carrier
    ) -> None:
        with pytest.raises(TypeError, match=r"project state, a carrier and options"):
            plan_init(MISSING, carrier, InitOptions())
        with pytest.raises(TypeError, match=r"project state, a carrier and options"):
            plan_init(ProjectState(), MISSING, InitOptions())
        with pytest.raises(TypeError, match=r"project state, a carrier and options"):
            plan_init(ProjectState(), carrier, MISSING)
