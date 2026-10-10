# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Uninstall removes EXACTLY what the installer wrote and nothing beside it. Every case here is a
"leave it alone" as much as it is a "remove it": a foreign directory, a line that is not the line we
added, a file a person has since written in.

Named after the Java port's ``UninstallPlannerTest`` so the two lists diff.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from narrativetrace_tooling.init.action import (
    Action,
    DeleteDirectory,
    DeleteFile,
    FileEdit,
    Refuse,
    ReplaceBlock,
)
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.options import InitOptions, Scope
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence, ProjectState
from narrativetrace_tooling.init.uninstall_planner import UNKNOWN_CARRIER, plan_uninstall

AGENTS_MD = Path("AGENTS.md")
CLAUDE_MD = Path("CLAUDE.md")
CURSOR_RULES = Path(".cursorrules")
DOCTOR_PAGE = Path(".agents/skills/doctor/SKILL.md")
DOCTOR_DIRECTORY = Path(".agents/skills/doctor")

COORDINATE = "narrativetrace-skills==1.2.3"

BLOCK = (
    f"<!-- narrativetrace:start {COORDINATE} -->\n## NarrativeTrace\n<!-- narrativetrace:end -->\n"
)

CREATED = "<!-- narrativetrace:created -->\n"

MISSING: Any = None


def plan(state: ProjectState) -> InitPlan:
    return plan_uninstall(state, InitOptions())


def action_on(a_plan: InitPlan, path: Path) -> Action | None:
    return next((action for action in a_plan.actions if action.path == path), None)


def after(a_plan: InitPlan, path: Path) -> str:
    found = action_on(a_plan, path)
    assert isinstance(found, FileEdit), f"no file edit on {path} in {a_plan.actions}"
    return found.after


def ours(coordinate: str = COORDINATE) -> InstalledSkill:
    return InstalledSkill(SkillFlavour.AGENTS, "doctor", Presence.OURS, coordinate, "page\n")


class TestTheSkills:
    def test_removes_a_skill_page_and_then_its_directory(self) -> None:
        result = plan(ProjectState(installed_skills=(ours(),)))

        assert isinstance(action_on(result, DOCTOR_PAGE), DeleteFile)
        directory = action_on(result, DOCTOR_DIRECTORY)
        assert isinstance(directory, DeleteDirectory)
        assert result.actions.index(directory) == 1, "the directory goes after the page it held"

    def test_removes_a_skill_installed_from_any_carrier_version(self) -> None:
        result = plan(ProjectState(installed_skills=(ours("narrativetrace-skills==0.0.1"),)))

        assert len(result.actions) == 2

    def test_leaves_a_skill_directory_somebody_else_owns_completely_alone(self) -> None:
        state = ProjectState(
            installed_skills=(
                InstalledSkill(SkillFlavour.AGENTS, "theirs", Presence.FOREIGN, body="page\n"),
                InstalledSkill(SkillFlavour.CLAUDE, "a-file", Presence.NOT_A_DIRECTORY),
            )
        )

        assert plan(state).actions == ()
        assert plan(state).carrier == UNKNOWN_CARRIER


class TestTheManagedSection:
    def test_removes_the_section_and_leaves_the_rest_byte_for_byte(self) -> None:
        text = "# Agents\n\n" + BLOCK + "\ntail\n"

        result = plan(ProjectState(agents_md=text))

        assert isinstance(action_on(result, AGENTS_MD), ReplaceBlock)
        assert after(result, AGENTS_MD) == "# Agents\n\ntail\n"

    def test_deletes_a_file_the_installer_created_once_nothing_of_it_is_left(self) -> None:
        result = plan(ProjectState(agents_md=CREATED + BLOCK))

        assert isinstance(action_on(result, AGENTS_MD), DeleteFile)
        assert after(result, AGENTS_MD) == ""

    def test_keeps_a_file_the_installer_created_once_somebody_else_has_written_in_it(self) -> None:
        """The blank line before "my own notes" is the SEPARATOR THAT PERSON TYPED, not ours: our
        own separator, when there is one, sits before our section and goes with it. Removing exactly
        what the installer wrote means leaving that line where it is."""
        result = plan(ProjectState(agents_md=CREATED + BLOCK + "\nmy own notes\n"))

        assert isinstance(action_on(result, AGENTS_MD), ReplaceBlock)
        assert after(result, AGENTS_MD) == "\nmy own notes\n"

    def test_never_deletes_a_file_the_installer_only_appended_to(self) -> None:
        result = plan(ProjectState(agents_md=BLOCK))

        assert isinstance(action_on(result, AGENTS_MD), ReplaceBlock)
        assert after(result, AGENTS_MD) == ""

    def test_leaves_a_file_with_no_section_of_ours_alone(self) -> None:
        assert plan(ProjectState(agents_md="# Agents\n")).actions == ()

    def test_refuses_a_file_with_two_sections(self) -> None:
        result = plan(ProjectState(agents_md=BLOCK + "\n" + BLOCK))

        assert isinstance(action_on(result, AGENTS_MD), Refuse)
        assert result.exit_code == 1

    def test_refuses_a_file_whose_markers_do_not_pair_up(self) -> None:
        result = plan(ProjectState(agents_md="<!-- narrativetrace:start -->\nx\n"))

        assert isinstance(action_on(result, AGENTS_MD), Refuse)

    def test_says_to_remove_it_by_hand_rather_than_naming_a_flag(self) -> None:
        """No flag can make "which of these two sections is ours" answerable, so the refusal names
        no flag — unlike every refusal on the install side. Asserted in full, not by fragment: this
        sentence is the one output of an uninstall a person acts on."""
        result = plan(ProjectState(agents_md=BLOCK + "\n" + BLOCK))
        refusal = action_on(result, AGENTS_MD)

        assert isinstance(refusal, Refuse)
        assert refusal.reason == (
            "AGENTS.md does not carry exactly one NarrativeTrace section — remove it by hand"
        )
        assert "--" not in refusal.reason


class TestTheImportLine:
    def test_removes_the_exact_import_line_it_added(self) -> None:
        result = plan(ProjectState(claude_md="# Project\n\n@AGENTS.md\n"))

        assert after(result, CLAUDE_MD) == "# Project\n"

    @pytest.mark.parametrize(
        "claude_md",
        ["# P\n\n@AGENTS.md  \n", "```\n@AGENTS.md\n```\n", "see `@AGENTS.md`\n"],
    )
    def test_leaves_a_line_that_is_not_the_exact_line_it_added(self, claude_md: str) -> None:
        assert plan(ProjectState(claude_md=claude_md)).actions == ()

    def test_does_nothing_when_there_is_no_vendor_context_file(self) -> None:
        assert plan(ProjectState()).actions == ()


class TestRuleFilesScopeAndThePlanItself:
    def test_removes_our_section_from_a_vendor_rule_file_but_never_the_file(self) -> None:
        state = ProjectState(marked_rule_files={".cursorrules": "# rules\n\n" + BLOCK})

        result = plan(state)

        assert isinstance(action_on(result, CURSOR_RULES), ReplaceBlock)
        assert after(result, CURSOR_RULES) == "# rules\n"

    def test_never_deletes_a_rule_file_even_when_our_section_was_all_of_it(self) -> None:
        state = ProjectState(marked_rule_files={".cursorrules": CREATED + BLOCK})

        result = plan(state)

        assert isinstance(action_on(result, CURSOR_RULES), ReplaceBlock)

    def test_removes_only_the_half_it_was_asked_for(self) -> None:
        state = ProjectState(installed_skills=(ours(),), agents_md=BLOCK)

        skills_only = plan_uninstall(state, dataclasses.replace(InitOptions(), scope=Scope.SKILLS))
        section_only = plan_uninstall(
            state, dataclasses.replace(InitOptions(), scope=Scope.AGENTS_MD)
        )

        assert action_on(skills_only, AGENTS_MD) is None
        assert len(skills_only.actions) == 2
        assert action_on(section_only, AGENTS_MD) is not None
        assert len(section_only.actions) == 1

    def test_names_the_carrier_the_project_was_installed_from(self) -> None:
        from_section = ProjectState(agents_md=BLOCK)
        from_skill = ProjectState(installed_skills=(ours(),))
        from_nothing = ProjectState()

        assert plan(from_section).carrier == COORDINATE
        assert plan(from_skill).carrier == COORDINATE
        assert plan(from_nothing).carrier.endswith("==unknown")

    def test_prefers_the_sections_stamp_over_a_skills_when_the_two_disagree(self) -> None:
        state = ProjectState(
            agents_md=BLOCK, installed_skills=(ours("narrativetrace-skills==0.0.1"),)
        )

        assert plan(state).carrier == COORDINATE

    def test_reports_the_unknown_carrier_when_the_section_carries_no_stamp(self) -> None:
        unstamped = "<!-- narrativetrace:start -->\nhand written\n<!-- narrativetrace:end -->\n"

        result = plan(ProjectState(agents_md=unstamped))

        assert result.carrier == UNKNOWN_CARRIER
        assert isinstance(action_on(result, AGENTS_MD), ReplaceBlock)

    def test_reports_the_unknown_carrier_when_the_section_cannot_be_read_at_all(self) -> None:
        """Two sections: no stamp can be trusted, so the plan is honest about the carrier AND
        refuses the file."""
        result = plan(ProjectState(agents_md=BLOCK + "\n" + BLOCK))

        assert result.carrier == UNKNOWN_CARRIER

    def test_an_uninstall_of_nothing_is_an_empty_plan_that_exits_zero(self) -> None:
        result = plan(ProjectState())

        assert result.is_empty is True
        assert result.exit_code == 0

    def test_carries_the_dry_run_flag(self) -> None:
        result = plan_uninstall(
            ProjectState(agents_md=BLOCK + "\n" + BLOCK),
            dataclasses.replace(InitOptions(), dry_run=True),
        )

        assert result.dry_run is True
        assert result.exit_code == 0

    def test_refuses_to_plan_without_a_snapshot_or_options(self) -> None:
        with pytest.raises(TypeError, match=r"project state and options"):
            plan_uninstall(MISSING, InitOptions())
        with pytest.raises(TypeError, match=r"project state and options"):
            plan_uninstall(ProjectState(), MISSING)


class TestWhatTheRegistryKeeps:
    """Rule 5, amended: an uninstall removes only what the installer created, and never FOLLOWS a
    link out of the project. The registry's own files — its lock file, its pages behind a link — are
    left exactly as they were.
    """

    def test_leaves_a_linked_skill_directory_entirely_alone(self) -> None:
        """Deleting the page behind it would delete the OPEN-STANDARD page a registry installed, and
        deleting the directory would delete the link's target."""
        state = ProjectState(
            installed_skills=(
                InstalledSkill(
                    SkillFlavour.CLAUDE,
                    "doctor",
                    Presence.LINKED_DIRECTORY,
                    body="page\n",
                    link="../../.agents/skills/doctor",
                ),
            )
        )

        result = plan_uninstall(state, InitOptions())

        assert result.actions == ()

    def test_leaves_a_linked_page_alone_too(self) -> None:
        state = ProjectState(
            installed_skills=(
                InstalledSkill(
                    SkillFlavour.CLAUDE,
                    "doctor",
                    Presence.LINKED_PAGE,
                    body="page\n",
                    link="../../.agents/skills/doctor/SKILL.md",
                ),
            )
        )

        assert plan_uninstall(state, InitOptions()).actions == ()

    def test_leaves_a_linked_page_alone_even_when_the_page_it_reaches_is_stamped_as_ours(
        self,
    ) -> None:
        """The stamp says the BYTES are ours; the link says the PATH is not, and only the path
        decides what may be deleted."""
        state = ProjectState(
            installed_skills=(
                InstalledSkill(
                    SkillFlavour.CLAUDE,
                    "doctor",
                    Presence.LINKED_DIRECTORY,
                    body=f"<!-- installed by narrativetrace init from {COORDINATE} —"
                    " edit the catalogue, not this file -->\n",
                    link="../../.agents/skills/doctor",
                ),
            )
        )

        assert plan_uninstall(state, InitOptions()).actions == ()

    def test_removes_our_own_install_beside_a_link_it_leaves(self) -> None:
        state = ProjectState(
            installed_skills=(
                ours(),
                InstalledSkill(
                    SkillFlavour.CLAUDE,
                    "doctor",
                    Presence.LINKED_DIRECTORY,
                    body="page\n",
                    link="../../.agents/skills/doctor",
                ),
            )
        )

        result = plan_uninstall(state, InitOptions())

        assert isinstance(action_on(result, DOCTOR_PAGE), DeleteFile)
        assert action_on(result, Path(".claude/skills/doctor/SKILL.md")) is None

    def test_says_nothing_about_a_flavour_whose_whole_install_root_is_a_link(self) -> None:
        state = ProjectState(linked_install_roots={SkillFlavour.CLAUDE: "../elsewhere/skills"})

        assert plan_uninstall(state, InitOptions()).actions == ()
