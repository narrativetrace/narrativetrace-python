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
