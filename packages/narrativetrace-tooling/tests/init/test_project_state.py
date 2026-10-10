# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The snapshot a test builds by hand — the reason every planner case is a unit test with no disk at
all. These cases cover the defaults, the lookup and the contract guards.

Named after the Java port's ``ProjectStateTest`` so the two lists diff. Java needs a builder because
it has no keyword arguments; here the snapshot is a frozen dataclass with defaults, so
``ProjectState()`` IS "an untouched project".
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from narrativetrace_tooling.init import project_state as project_state_module
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.project_state import (
    DEFAULT_OUTPUT_DIRECTORY,
    InstalledSkill,
    Presence,
    ProjectState,
)

MISSING: Any = None

COORDINATE = "narrativetrace-skills==1.0.0"


def ours(name: str, flavour: SkillFlavour = SkillFlavour.AGENTS) -> InstalledSkill:
    return InstalledSkill(flavour, name, Presence.OURS, COORDINATE, "body")


@pytest.fixture
def populated() -> Iterator[ProjectState]:
    state = ProjectState(agents_md="# A\n", installed_skills=(ours("doctor"),))
    assert project_state_module._invariant(state), "the snapshot is inconsistent before the test"
    yield state
    assert project_state_module._invariant(state), "the test left the snapshot inconsistent"


class TestTheSnapshot:
    def test_an_untouched_project_is_the_default(self) -> None:
        state = ProjectState()

        assert state.agents_md is None
        assert state.claude_md is None
        assert state.claude_directory is False
        assert state.uv_project is False
        assert state.installed_skills == ()
        assert dict(state.marked_rule_files) == {}
        assert state.output_directory == DEFAULT_OUTPUT_DIRECTORY
        assert project_state_module._invariant(state) is True

    def test_the_default_output_directory_is_the_runtimes_own(self) -> None:
        assert DEFAULT_OUTPUT_DIRECTORY == "narrative-traces"

    def test_keeps_everything_it_was_given(self) -> None:
        state = ProjectState(
            agents_md="# A\n",
            claude_md="# C\n",
            claude_directory=True,
            uv_project=True,
            output_directory="out",
            marked_rule_files={".cursorrules": "rules"},
            installed_skills=(ours("doctor"),),
        )

        assert state.agents_md == "# A\n"
        assert state.claude_md == "# C\n"
        assert state.claude_directory is True
        assert state.uv_project is True
        assert state.output_directory == "out"
        assert state.marked_rule_files[".cursorrules"] == "rules"
        assert state.installed_skill(SkillFlavour.AGENTS, "doctor") is not None
        assert state.installed_skill(SkillFlavour.CLAUDE, "doctor") is None

    def test_keeps_its_collections_immutable(self, populated: ProjectState) -> None:
        assert isinstance(populated.installed_skills, tuple)
        with pytest.raises(TypeError):
            populated.marked_rule_files["x"] = "y"  # type: ignore[index]

    def test_refuses_to_describe_the_same_path_twice(self) -> None:
        with pytest.raises(AssertionError):
            ProjectState(installed_skills=(ours("doctor"), ours("doctor")))

    def test_describes_the_same_name_under_each_flavour_independently(self) -> None:
        state = ProjectState(installed_skills=(ours("doctor"), ours("doctor", SkillFlavour.CLAUDE)))

        assert len(state.installed_skills) == 2

    def test_refuses_a_blank_output_directory(self) -> None:
        with pytest.raises(ValueError, match=r"where traces land"):
            ProjectState(output_directory=" ")


class TestAnInstalledSkill:
    def test_names_the_page_and_the_directory_under_its_own_install_root(self) -> None:
        agents = ours("narrativetrace-doctor")
        vendor = ours("narrativetrace-doctor", SkillFlavour.CLAUDE)

        assert agents.directory == Path(".agents/skills/narrativetrace-doctor")
        assert agents.page == Path(".agents/skills/narrativetrace-doctor/SKILL.md")
        assert vendor.page == Path(".claude/skills/narrativetrace-doctor/SKILL.md")

    def test_refuses_an_installed_skill_that_contradicts_itself(self) -> None:
        with pytest.raises(ValueError, match=r"carries its coordinate"):
            InstalledSkill(SkillFlavour.AGENTS, "d", Presence.OURS, "", "body")
        with pytest.raises(TypeError, match=r"flavour and a presence"):
            InstalledSkill(MISSING, "d", Presence.FOREIGN)
        with pytest.raises(TypeError, match=r"flavour and a presence"):
            InstalledSkill(SkillFlavour.AGENTS, "d", MISSING)
        with pytest.raises(ValueError, match=r"name must not be blank"):
            InstalledSkill(SkillFlavour.AGENTS, " ", Presence.FOREIGN)
        with pytest.raises(TypeError, match=r"never None"):
            InstalledSkill(SkillFlavour.AGENTS, "d", Presence.FOREIGN, MISSING)
        with pytest.raises(TypeError, match=r"never None"):
            InstalledSkill(SkillFlavour.AGENTS, "d", Presence.FOREIGN, "", MISSING)

    def test_a_foreign_or_missing_directory_carries_no_coordinate_and_that_is_legal(self) -> None:
        foreign = InstalledSkill(SkillFlavour.AGENTS, "theirs", Presence.FOREIGN, body="page\n")
        not_a_directory = InstalledSkill(SkillFlavour.CLAUDE, "a-file", Presence.NOT_A_DIRECTORY)

        assert foreign.coordinate == ""
        assert not_a_directory.body == ""


class TestASkillBehindALink:
    """Rule 18's half of the snapshot. ``npx skills add`` writes the open-standard pages for real
    and makes ``.claude/skills/<name>`` a LINK to them, so the two linked presences are what stop
    the planner from ever writing the vendor flavour through one.
    """

    def test_a_linked_directory_says_where_the_link_points_and_the_link_sits_on_it(self) -> None:
        linked = InstalledSkill(
            SkillFlavour.CLAUDE,
            "doctor",
            Presence.LINKED_DIRECTORY,
            body="page\n",
            link="../../.agents/skills/doctor",
        )

        assert linked.link == "../../.agents/skills/doctor"
        assert linked.linked_at == Path(".claude/skills/doctor")

    def test_a_linked_page_puts_the_link_on_the_page_not_the_directory(self) -> None:
        linked = InstalledSkill(
            SkillFlavour.CLAUDE, "doctor", Presence.LINKED_PAGE, body="page\n", link="../SKILL.md"
        )

        assert linked.linked_at == Path(".claude/skills/doctor/SKILL.md")

    def test_a_linked_presence_must_name_what_the_link_points_at(self) -> None:
        with pytest.raises(ValueError, match=r"names what the link points at"):
            InstalledSkill(SkillFlavour.CLAUDE, "doctor", Presence.LINKED_DIRECTORY)

    def test_only_a_linked_presence_may_name_one(self) -> None:
        with pytest.raises(ValueError, match=r"names what the link points at"):
            InstalledSkill(SkillFlavour.AGENTS, "doctor", Presence.FOREIGN, link="somewhere")

    def test_asking_an_unlinked_skill_where_its_link_sits_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match=r"nothing links to \.agents/skills/doctor"):
            _ = ours("doctor").linked_at

    def test_a_link_that_reaches_no_page_of_ours_carries_an_empty_body(self) -> None:
        """Dangling, out of the project, or a chain the filesystem will not follow — the installer
        treats all three as reaching no page at all."""
        dangling = InstalledSkill(
            SkillFlavour.CLAUDE, "doctor", Presence.LINKED_DIRECTORY, link="/nowhere"
        )

        assert dangling.body == ""


class TestAFlavourWhoseWholeInstallRootIsALink:
    """Rule 20. One link is one decision, so the snapshot reports it once per flavour rather than
    once per skill — nothing may be written into that flavour at all, present or not."""

    def test_names_what_the_root_points_at(self) -> None:
        state = ProjectState(linked_install_roots={SkillFlavour.CLAUDE: "../elsewhere"})

        assert state.linked_install_root(SkillFlavour.CLAUDE) == "../elsewhere"
        assert state.linked_install_root(SkillFlavour.AGENTS) is None

    def test_an_untouched_project_has_no_linked_root(self) -> None:
        assert ProjectState().linked_install_root(SkillFlavour.AGENTS) is None

    def test_keeps_the_mapping_immutable(self) -> None:
        state = ProjectState(linked_install_roots={SkillFlavour.CLAUDE: "../elsewhere"})

        with pytest.raises(TypeError):
            state.linked_install_roots[SkillFlavour.AGENTS] = "x"  # type: ignore[index]

    def test_refuses_a_skill_listed_under_a_flavour_whose_root_is_a_link(self) -> None:
        """Whatever was found there was found THROUGH the link, so listing it would invite exactly
        the write the refusal exists to prevent."""
        with pytest.raises(AssertionError):
            ProjectState(
                installed_skills=(ours("doctor", SkillFlavour.CLAUDE),),
                linked_install_roots={SkillFlavour.CLAUDE: "../elsewhere"},
            )
