# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""D2 — a platform's pointer is written only when the platform's marker is in the project, adopted
when it is already ours, refused when it is somebody's, and never written through a link.

Named after the Java port's ``PlatformPointerPlannerTest`` so the two lists diff. The planner is
pure: a snapshot is built by hand and the plan read back.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import carriers
import pytest

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.action import (
    Action,
    AdoptPage,
    AppendBlock,
    CreateFile,
    FileEdit,
    Refuse,
    ReplaceBlock,
)
from narrativetrace_tooling.init.agents_md_block import render_agents_md_block
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.cursor_rule import render_cursor_rule
from narrativetrace_tooling.init.init_planner import plan_init
from narrativetrace_tooling.init.options import InitOptions, Scope
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import ProjectState
from narrativetrace_tooling.platforms import table as platform_table

REPLIT_MD = Path("replit.md")
CURSOR_RULE = Path(".cursor/rules/narrativetrace.mdc")
BOM = "﻿"


@pytest.fixture
def carrier(tmp_path: Path) -> Carrier:
    return carriers.fake(tmp_path, "doctor")


def plan(carrier: Carrier, state: ProjectState, options: InitOptions | None = None) -> InitPlan:
    return plan_init(state, carrier, options or InitOptions())


def on(a_plan: InitPlan, path: Path) -> Action | None:
    return next((action for action in a_plan.actions if action.path == path), None)


def after(a_plan: InitPlan, path: Path) -> str:
    found = on(a_plan, path)
    assert isinstance(found, FileEdit), f"no file edit on {path} in {a_plan.actions}"
    return found.after


def cursor_rule(coordinate: str) -> str:
    pointer = platform_table.row("cursor").pointer
    assert isinstance(pointer, platform_table.Rule)
    return render_cursor_rule(pointer.text, coordinate)


class TestNoMarkerNoPointer:
    def test_writes_no_pointer_for_a_project_on_no_platform(self, carrier: Carrier) -> None:
        result = plan(carrier, ProjectState())

        assert on(result, REPLIT_MD) is None
        assert on(result, CURSOR_RULE) is None

    def test_writes_no_pointer_for_platforms_that_need_none(self, carrier: Carrier) -> None:
        state = ProjectState(detected_platforms={"antigravity", "github-copilot", "claude-code"})

        paths = {action.path for action in plan(carrier, state).actions}

        assert REPLIT_MD not in paths
        assert CURSOR_RULE not in paths

    def test_a_skills_only_run_writes_no_pointer(self, carrier: Carrier) -> None:
        state = ProjectState(detected_platforms={"cursor", "replit"})
        options = dataclasses.replace(InitOptions(), scope=Scope.SKILLS)

        result = plan(carrier, state, options)

        assert on(result, REPLIT_MD) is None
        assert on(result, CURSOR_RULE) is None

    def test_an_agents_md_only_run_still_writes_the_pointers(self, carrier: Carrier) -> None:
        state = ProjectState(detected_platforms={"cursor", "replit"})
        options = dataclasses.replace(InitOptions(), scope=Scope.AGENTS_MD)

        result = plan(carrier, state, options)

        assert isinstance(on(result, REPLIT_MD), CreateFile)
        assert isinstance(on(result, CURSOR_RULE), CreateFile)


class TestReplit:
    def test_creates_replit_md_with_the_managed_section_when_only_dot_replit_marks_the_project(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(detected_platforms={"replit"})

        result = plan(carrier, state)

        assert isinstance(on(result, REPLIT_MD), CreateFile)
        assert after(result, REPLIT_MD) == (
            marked_block.CREATED_NOTE + "\n" + render_agents_md_block(carrier, state)
        )

    def test_refuses_to_append_to_an_existing_replit_md_without_permission(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(
            detected_platforms={"replit"}, pointer_files={"replit.md": "# My notes\n"}
        )

        assert isinstance(on(plan(carrier, state), REPLIT_MD), Refuse)

    def test_appends_the_section_to_an_existing_replit_md_when_allowed(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(
            detected_platforms={"replit"}, pointer_files={"replit.md": "# My notes\n"}
        )
        options = dataclasses.replace(InitOptions(), write_existing=True)

        result = plan(carrier, state, options)

        assert isinstance(on(result, REPLIT_MD), AppendBlock)
        assert after(result, REPLIT_MD) == "# My notes\n\n" + render_agents_md_block(carrier, state)

    def test_leaves_a_current_replit_md_alone_and_refreshes_a_stale_one(
        self, carrier: Carrier
    ) -> None:
        base = ProjectState(detected_platforms={"replit"})
        current = marked_block.CREATED_NOTE + "\n" + render_agents_md_block(carrier, base)
        up_to_date = dataclasses.replace(base, pointer_files={"replit.md": current})
        assert on(plan(carrier, up_to_date), REPLIT_MD) is None

        stale = current.replace(carrier.coordinate, "narrativetrace-skills==0.0.1")
        behind = dataclasses.replace(base, pointer_files={"replit.md": stale})

        assert isinstance(on(plan(carrier, behind), REPLIT_MD), ReplaceBlock)
        assert after(plan(carrier, behind), REPLIT_MD) == current

    def test_refuses_a_replit_md_whose_section_never_closes_even_with_write_existing(
        self, carrier: Carrier
    ) -> None:
        text = "# Notes\n<!-- narrativetrace:start x==1 -->\nno end\n"
        state = ProjectState(detected_platforms={"replit"}, pointer_files={"replit.md": text})
        options = dataclasses.replace(InitOptions(), write_existing=True)

        assert isinstance(on(plan(carrier, state, options), REPLIT_MD), Refuse)

    def test_a_stale_section_after_a_byte_order_mark_is_refreshed_and_the_mark_survives(
        self, carrier: Carrier
    ) -> None:
        base = ProjectState(detected_platforms={"replit"})
        block = render_agents_md_block(carrier, base)
        stale = BOM + block.replace(carrier.coordinate, "narrativetrace-skills==0.0.1")
        state = dataclasses.replace(base, pointer_files={"replit.md": stale})

        assert after(plan(carrier, state), REPLIT_MD) == BOM + block


class TestCursor:
    def test_creates_the_rule_when_the_cursor_directory_is_there(self, carrier: Carrier) -> None:
        state = ProjectState(detected_platforms={"cursor"})

        result = plan(carrier, state)

        assert isinstance(on(result, CURSOR_RULE), CreateFile)
        assert after(result, CURSOR_RULE) == cursor_rule(carrier.coordinate)

    def test_the_rule_is_one_rule_and_not_a_copy_of_any_skill_page(self, carrier: Carrier) -> None:
        rule = cursor_rule(carrier.coordinate)

        assert rule.startswith("---\n")
        assert "alwaysApply: true" in rule
        assert ".agents/skills" in rule
        assert "narrativetrace-doctor" not in rule
        assert marked_block.scan(rule).has_exactly_one_region()

    def test_leaves_a_current_rule_alone_and_refreshes_a_stale_one(self, carrier: Carrier) -> None:
        current = ProjectState(
            detected_platforms={"cursor"},
            pointer_files={str(CURSOR_RULE): cursor_rule(carrier.coordinate)},
        )
        assert on(plan(carrier, current), CURSOR_RULE) is None

        stale = ProjectState(
            detected_platforms={"cursor"},
            pointer_files={str(CURSOR_RULE): cursor_rule("narrativetrace-skills==0.0.1")},
        )

        assert isinstance(on(plan(carrier, stale), CURSOR_RULE), ReplaceBlock)
        assert after(plan(carrier, stale), CURSOR_RULE) == cursor_rule(carrier.coordinate)

    def test_adopts_the_unstamped_rule_the_plugin_ships_without_asking_for_force(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(
            detected_platforms={"cursor"}, pointer_files={str(CURSOR_RULE): cursor_rule("")}
        )

        result = plan(carrier, state)

        assert isinstance(on(result, CURSOR_RULE), AdoptPage)
        assert after(result, CURSOR_RULE) == cursor_rule(carrier.coordinate)

    def test_adopts_the_plugins_rule_saved_with_crlf_line_endings(self, carrier: Carrier) -> None:
        crlf = cursor_rule("").replace("\n", "\r\n")
        state = ProjectState(detected_platforms={"cursor"}, pointer_files={str(CURSOR_RULE): crlf})

        assert isinstance(on(plan(carrier, state), CURSOR_RULE), AdoptPage)

    def test_a_current_rule_saved_with_crlf_is_not_rewritten(self, carrier: Carrier) -> None:
        crlf = cursor_rule(carrier.coordinate).replace("\n", "\r\n")
        state = ProjectState(detected_platforms={"cursor"}, pointer_files={str(CURSOR_RULE): crlf})

        assert on(plan(carrier, state), CURSOR_RULE) is None

    def test_refuses_a_rule_file_somebody_else_wrote_at_our_path(self, carrier: Carrier) -> None:
        mine = "---\nalwaysApply: true\n---\nmine\n"
        state = ProjectState(detected_platforms={"cursor"}, pointer_files={str(CURSOR_RULE): mine})

        action = on(plan(carrier, state), CURSOR_RULE)

        assert isinstance(action, Refuse)
        assert "not written by narrativetrace" in action.reason

    def test_refuses_a_rule_file_with_two_sections_and_does_not_guess(
        self, carrier: Carrier
    ) -> None:
        two = (
            cursor_rule(carrier.coordinate)
            + marked_block.START
            + " -->\nx\n"
            + marked_block.END
            + "\n"
        )
        state = ProjectState(detected_platforms={"cursor"}, pointer_files={str(CURSOR_RULE): two})

        assert isinstance(on(plan(carrier, state), CURSOR_RULE), Refuse)

    def test_keeps_a_rule_the_user_wrote_below_ours_when_refreshing(self, carrier: Carrier) -> None:
        stale = cursor_rule("narrativetrace-skills==0.0.1") + "\nMy own rule.\n"
        state = ProjectState(detected_platforms={"cursor"}, pointer_files={str(CURSOR_RULE): stale})

        assert after(plan(carrier, state), CURSOR_RULE) == (
            cursor_rule(carrier.coordinate) + "\nMy own rule.\n"
        )


class TestLinksAndTheMixedCase:
    def test_refuses_a_pointer_whose_path_runs_through_a_symbolic_link(
        self, carrier: Carrier
    ) -> None:
        state = ProjectState(
            detected_platforms={"cursor", "replit"},
            pointers_behind_links={str(CURSOR_RULE), "replit.md"},
        )

        result = plan(carrier, state)

        assert isinstance(on(result, CURSOR_RULE), Refuse)
        refusal = on(result, REPLIT_MD)
        assert isinstance(refusal, Refuse)
        assert "symbolic link" in refusal.reason

    def test_plans_both_pointers_when_two_markers_are_present_at_once(
        self, carrier: Carrier
    ) -> None:
        result = plan(carrier, ProjectState(detected_platforms={"cursor", "replit"}))

        assert isinstance(on(result, REPLIT_MD), CreateFile)
        assert isinstance(on(result, CURSOR_RULE), CreateFile)

    def test_a_second_run_over_the_installed_project_plans_nothing_for_the_pointers(
        self, carrier: Carrier
    ) -> None:
        base = ProjectState(detected_platforms={"cursor", "replit"})
        installed = dataclasses.replace(
            base,
            pointer_files={
                "replit.md": marked_block.CREATED_NOTE
                + "\n"
                + render_agents_md_block(carrier, base),
                str(CURSOR_RULE): cursor_rule(carrier.coordinate),
            },
        )

        result = plan(carrier, installed)

        assert on(result, REPLIT_MD) is None
        assert on(result, CURSOR_RULE) is None
