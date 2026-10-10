# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The refresh plan: the narrow, never-creating half of an install. Pure, like the other two
planners, so every rule here is a unit test with no disk at all.

Named after the Java port's ``RefreshPlannerTest`` so the two lists diff; it also carries that
port's ``RefreshPlannerAdversarialM3Test`` cases, which are the same planner's feature
combinations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import carriers
import pytest

from narrativetrace_tooling.init import provenance
from narrativetrace_tooling.init.action import Action, FileEdit, ReplaceBlock
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence, ProjectState
from narrativetrace_tooling.init.refresh_planner import is_installed, plan_refresh

OLD = "narrativetrace-skills==0.0.1"

DOCTOR_PAGE = Path(".agents/skills/doctor/SKILL.md")
AGENTS_MD = Path("AGENTS.md")
CLAUDE_MD = Path("CLAUDE.md")

MISSING: Any = None


@pytest.fixture
def carrier(tmp_path: Path) -> Carrier:
    return carriers.fake(tmp_path, "doctor")


def ours(name: str, coordinate: str) -> InstalledSkill:
    return InstalledSkill(
        SkillFlavour.AGENTS,
        name,
        Presence.OURS,
        coordinate,
        provenance.stamp(carriers.body(name, SkillFlavour.AGENTS), coordinate),
    )


def paths(plan: InitPlan) -> list[Path]:
    return [action.path for action in plan.actions]


def after(plan: InitPlan, path: Path) -> str:
    found: Action | None = next((a for a in plan.actions if a.path == path), None)
    assert isinstance(found, FileEdit)
    return found.after


class TestWhatARefreshRewrites:
    def test_plans_nothing_for_a_project_that_never_ran_init(self, carrier: Carrier) -> None:
        assert plan_refresh(ProjectState(), carrier).is_empty is True

    def test_rewrites_a_stale_skill_page_in_place(self, carrier: Carrier) -> None:
        state = ProjectState(installed_skills=(ours("doctor", OLD),))

        plan = plan_refresh(state, carrier)

        assert DOCTOR_PAGE in paths(plan)
        assert all(isinstance(action, ReplaceBlock) for action in plan.actions)

    def test_plans_nothing_when_every_installed_skill_already_carries_the_coordinate(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(installed_skills=(ours("doctor", carrier.coordinate),))

        assert plan_refresh(state, carrier).is_empty is True

    def test_leaves_a_page_alone_when_its_stamp_matches_however_it_has_been_edited(
        self, carrier: Carrier
    ) -> None:
        """A stamp that already matches means a refresh has nothing to say, whatever the page now
        contains. Somebody editing an installed page has their reasons; silently reverting them
        would be the one thing a refresh must not do. Re-run ``init`` to overwrite it
        deliberately."""
        edited = InstalledSkill(
            SkillFlavour.AGENTS,
            "doctor",
            Presence.OURS,
            carrier.coordinate,
            provenance.stamp(
                "---\nname: doctor\n---\n\nsomebody's own words\n", carrier.coordinate
            ),
        )

        assert plan_refresh(ProjectState(installed_skills=(edited,)), carrier).is_empty is True

    def test_never_creates_a_skill_the_project_does_not_have(self, tmp_path: Path) -> None:
        two = carriers.fake(tmp_path / "two", "doctor", "clarity")
        state = ProjectState(installed_skills=(ours("doctor", OLD),))

        assert paths(plan_refresh(state, two)) == [DOCTOR_PAGE]

    def test_refreshes_the_stale_page_and_leaves_a_skill_the_carrier_does_not_carry(
        self, carrier: Carrier
    ) -> None:
        """A project carrying a skill this carrier never heard of, beside a stale one it does: the
        stale page is rewritten and the stranger is left entirely alone. Neither half is new on its
        own — a refresh that reached for the CATALOGUE instead of the project would only show it
        here, with both at once."""
        state = ProjectState(
            installed_skills=(ours("doctor", OLD), ours("harvester", carriers.FAKE_COORDINATE))
        )

        assert paths(plan_refresh(state, carrier)) == [DOCTOR_PAGE]

    def test_never_appends_a_section_to_an_agents_md_that_carries_none(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(installed_skills=(ours("doctor", OLD),), agents_md="# Agents\n")

        assert AGENTS_MD not in paths(plan_refresh(state, carrier))

    def test_rewrites_our_own_section_beside_the_pages(self, carrier: Carrier) -> None:
        agents = (
            f"# Agents\n\n<!-- narrativetrace:start {OLD} -->\nstale\n<!-- narrativetrace:end -->\n"
        )
        state = ProjectState(installed_skills=(ours("doctor", OLD),), agents_md=agents)

        plan = plan_refresh(state, carrier)

        assert AGENTS_MD in paths(plan)
        assert carrier.coordinate in after(plan, AGENTS_MD)

    def test_never_adds_the_import_line_to_a_vendor_context_file(self, carrier: Carrier) -> None:
        state = ProjectState(installed_skills=(ours("doctor", OLD),), claude_md="# Claude\n")

        assert CLAUDE_MD not in paths(plan_refresh(state, carrier))

    def test_never_touches_a_skill_directory_somebody_else_owns(self, carrier: Carrier) -> None:
        state = ProjectState(
            installed_skills=(
                ours("doctor", OLD),
                InstalledSkill(SkillFlavour.AGENTS, "theirs", Presence.FOREIGN, body="# theirs\n"),
            )
        )

        assert paths(plan_refresh(state, carrier)) == [DOCTOR_PAGE]

    def test_never_carries_a_refusal(self, tmp_path: Path) -> None:
        two = carriers.fake(tmp_path / "two", "doctor", "clarity")
        state = ProjectState(
            installed_skills=(
                ours("doctor", OLD),
                InstalledSkill(SkillFlavour.AGENTS, "clarity", Presence.NOT_A_DIRECTORY),
            ),
            agents_md=(
                "# Agents\n\n<!-- narrativetrace:start -->\na\n<!-- narrativetrace:end -->\n"
                "<!-- narrativetrace:start -->\nb\n<!-- narrativetrace:end -->\n"
            ),
        )

        plan = plan_refresh(state, two)

        assert plan.has_refusals is False
        assert plan.exit_code == 0

    def test_is_never_a_dry_run(self, carrier: Carrier) -> None:
        """A refresh has no preview mode of its own: it is the internal shape of a real run, and a
        caller that wants a preview asks the install planner for one."""
        assert plan_refresh(ProjectState(), carrier).dry_run is False


class TestWhetherAProjectCarriesAnInstall:
    def test_knows_whether_a_project_carries_an_install_of_ours_at_all(self) -> None:
        assert is_installed(ProjectState()) is False
        assert is_installed(ProjectState(installed_skills=(ours("doctor", OLD),))) is True

    def test_a_skill_directory_somebody_else_owns_is_not_an_install_of_ours(self) -> None:
        state = ProjectState(
            installed_skills=(
                InstalledSkill(SkillFlavour.AGENTS, "theirs", Presence.FOREIGN, body="# theirs\n"),
                InstalledSkill(SkillFlavour.CLAUDE, "gone", Presence.NOT_A_DIRECTORY),
            )
        )

        assert is_installed(state) is False

    def test_a_managed_section_alone_is_not_an_install_of_ours(self) -> None:
        """The section is a pointer; the pages are the install. A project whose ``AGENTS.md`` was
        hand-edited to carry our markers has installed nothing."""
        state = ProjectState(
            agents_md="<!-- narrativetrace:start -->\nx\n<!-- narrativetrace:end -->\n"
        )

        assert is_installed(state) is False


class TestGuards:
    def test_refuses_to_answer_whether_nothing_is_installed(self) -> None:
        with pytest.raises(TypeError, match=r"needs a project state"):
            is_installed(MISSING)

    def test_refuses_to_plan_without_a_state_or_a_carrier(self, carrier: Carrier) -> None:
        with pytest.raises(TypeError, match=r"project state and a carrier"):
            plan_refresh(MISSING, carrier)
        with pytest.raises(TypeError, match=r"project state and a carrier"):
            plan_refresh(ProjectState(), MISSING)


class TestARefreshNeverAdopts:
    """A BUILD may keep an install current; it may never START one, and adoption is starting one.

    The tree is deliberately part registry and part one-release-stale install: a tree with nothing
    to refresh would also pass against a refresh that did nothing at all.
    """

    def test_rewrites_the_stale_page_of_ours_and_leaves_the_registrys_pages_alone(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(
            claude_directory=True,
            installed_skills=(
                ours("doctor", OLD),
                InstalledSkill(
                    SkillFlavour.CLAUDE,
                    "doctor",
                    Presence.FOREIGN,
                    body=carriers.body("doctor", SkillFlavour.CLAUDE),
                ),
            ),
        )

        plan = plan_refresh(state, carrier)

        assert paths(plan) == [DOCTOR_PAGE]
        assert all(isinstance(action, ReplaceBlock) for action in plan.actions)

    def test_drops_the_link_replacement_an_install_would_have_planned(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(
            claude_directory=True,
            installed_skills=(
                ours("doctor", OLD),
                InstalledSkill(
                    SkillFlavour.CLAUDE,
                    "doctor",
                    Presence.LINKED_DIRECTORY,
                    body=carriers.body("doctor", SkillFlavour.AGENTS),
                    link="../../.agents/skills/doctor",
                ),
            ),
        )

        plan = plan_refresh(state, carrier)

        assert paths(plan) == [DOCTOR_PAGE]

    def test_a_project_whose_pages_are_all_a_registrys_carries_no_install_of_ours(
        self, carrier: Carrier
    ) -> None:
        """So no carrier is ever resolved for it, and a refresh has nothing to be stale against."""
        state = ProjectState(
            installed_skills=(
                InstalledSkill(
                    SkillFlavour.AGENTS,
                    "doctor",
                    Presence.FOREIGN,
                    body=carriers.body("doctor", SkillFlavour.AGENTS),
                ),
            )
        )

        assert is_installed(state) is False
        assert plan_refresh(state, carrier).is_empty is True

    def test_a_project_whose_only_skill_is_behind_a_link_carries_no_install_of_ours_either(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(
            installed_skills=(
                InstalledSkill(
                    SkillFlavour.CLAUDE,
                    "doctor",
                    Presence.LINKED_DIRECTORY,
                    body=carriers.body("doctor", SkillFlavour.AGENTS),
                    link="../../.agents/skills/doctor",
                ),
            )
        )

        assert is_installed(state) is False
        assert plan_refresh(state, carrier).is_empty is True
