# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Uninstall removes exactly the platform pointers the installer wrote — whether or not the
platform's marker is still there — and nothing beside them.

Named after the Java port's ``PlatformPointerUninstallTest`` so the two lists diff.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.action import (
    Action,
    DeleteFile,
    FileEdit,
    Refuse,
    ReplaceBlock,
)
from narrativetrace_tooling.init.cursor_rule import FRONTMATTER
from narrativetrace_tooling.init.options import InitOptions, Scope
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import ProjectState
from narrativetrace_tooling.init.uninstall_planner import plan_uninstall

REPLIT_MD = Path("replit.md")
CURSOR_RULE = Path(".cursor/rules/narrativetrace.mdc")
COORDINATE = "narrativetrace-skills==1.2.3"
SECTION = (
    f"<!-- narrativetrace:start {COORDINATE} -->\n## NarrativeTrace\n<!-- narrativetrace:end -->\n"
)
RULE_SECTION = (
    f"<!-- narrativetrace:start {COORDINATE} -->\nRead them.\n<!-- narrativetrace:end -->\n"
)
CREATED = marked_block.CREATED_NOTE + "\n"
BOM = "﻿"


def plan(state: ProjectState, options: InitOptions | None = None) -> InitPlan:
    return plan_uninstall(state, options or InitOptions())


def on(a_plan: InitPlan, path: Path) -> Action | None:
    return next((action for action in a_plan.actions if action.path == path), None)


def after(a_plan: InitPlan, path: Path) -> str:
    found = on(a_plan, path)
    assert isinstance(found, FileEdit), f"no file edit on {path} in {a_plan.actions}"
    return found.after


def replit(text: str) -> ProjectState:
    return ProjectState(pointer_files={"replit.md": text})


def cursor(text: str) -> ProjectState:
    return ProjectState(pointer_files={str(CURSOR_RULE): text})


class TestReplitMd:
    def test_deletes_a_replit_md_the_installer_created(self) -> None:
        text = CREATED + SECTION

        assert on(plan(replit(text)), REPLIT_MD) == DeleteFile(REPLIT_MD, text)

    def test_keeps_the_notes_written_below_a_created_replit_md(self) -> None:
        text = CREATED + SECTION + "\nMy notes.\n"

        result = plan(replit(text))

        assert isinstance(on(result, REPLIT_MD), ReplaceBlock)
        assert after(result, REPLIT_MD) == "\nMy notes.\n"

    def test_keeps_a_replit_md_the_installer_only_appended_to(self) -> None:
        result = plan(replit("# Notes\n\n" + SECTION))

        assert after(result, REPLIT_MD) == "# Notes\n"

    def test_deletes_a_created_replit_md_saved_with_a_byte_order_mark(self) -> None:
        text = BOM + CREATED + SECTION

        assert on(plan(replit(text)), REPLIT_MD) == DeleteFile(REPLIT_MD, text)

    def test_removes_the_section_from_a_crlf_replit_md_in_crlf(self) -> None:
        text = "# Notes\r\n\r\n" + SECTION.replace("\n", "\r\n")

        assert after(plan(replit(text)), REPLIT_MD) == "# Notes\r\n"

    def test_refuses_a_replit_md_with_two_sections_and_leaves_it_alone(self) -> None:
        result = plan(replit(SECTION + "\n" + SECTION))

        assert isinstance(on(result, REPLIT_MD), Refuse)

    def test_leaves_a_replit_md_with_no_section_of_ours_alone(self) -> None:
        assert on(plan(replit("# Notes\n")), REPLIT_MD) is None


class TestCursorRule:
    def test_deletes_a_rule_file_that_is_nothing_but_the_frontmatter_once_ours_is_gone(
        self,
    ) -> None:
        text = FRONTMATTER + RULE_SECTION

        assert on(plan(cursor(text)), CURSOR_RULE) == DeleteFile(CURSOR_RULE, text)

    def test_keeps_a_rule_the_user_added_below_ours(self) -> None:
        text = FRONTMATTER + RULE_SECTION + "\nMy own rule.\n"

        result = plan(cursor(text))

        assert isinstance(on(result, CURSOR_RULE), ReplaceBlock)
        assert after(result, CURSOR_RULE) == FRONTMATTER + "\nMy own rule.\n"

    def test_deletes_a_rule_the_user_converted_to_crlf(self) -> None:
        text = (FRONTMATTER + RULE_SECTION).replace("\n", "\r\n")

        assert on(plan(cursor(text)), CURSOR_RULE) == DeleteFile(CURSOR_RULE, text)

    def test_deletes_a_rule_saved_with_a_byte_order_mark(self) -> None:
        text = BOM + FRONTMATTER + RULE_SECTION

        assert on(plan(cursor(text)), CURSOR_RULE) == DeleteFile(CURSOR_RULE, text)

    def test_keeps_a_rule_whose_frontmatter_the_user_edited(self) -> None:
        text = FRONTMATTER.replace("alwaysApply: true", "alwaysApply: false") + RULE_SECTION

        assert isinstance(on(plan(cursor(text)), CURSOR_RULE), ReplaceBlock)

    def test_refuses_a_rule_with_two_sections(self) -> None:
        result = plan(cursor(FRONTMATTER + RULE_SECTION + RULE_SECTION))

        assert isinstance(on(result, CURSOR_RULE), Refuse)

    def test_leaves_a_rule_file_with_no_section_of_ours_alone(self) -> None:
        assert on(plan(cursor("---\nalwaysApply: true\n---\nmine\n")), CURSOR_RULE) is None


class TestScopeAndLinks:
    def test_removes_the_pointers_even_when_no_platform_marker_is_left(self) -> None:
        state = ProjectState(
            pointer_files={
                "replit.md": CREATED + SECTION,
                str(CURSOR_RULE): FRONTMATTER + RULE_SECTION,
            }
        )

        result = plan(state)

        assert isinstance(on(result, REPLIT_MD), DeleteFile)
        assert isinstance(on(result, CURSOR_RULE), DeleteFile)

    def test_a_skills_only_uninstall_leaves_the_pointers(self) -> None:
        state = replit(CREATED + SECTION)
        options = dataclasses.replace(InitOptions(), scope=Scope.SKILLS)

        assert on(plan(state, options), REPLIT_MD) is None

    def test_never_touches_a_pointer_behind_a_link(self) -> None:
        state = ProjectState(pointers_behind_links={"replit.md", str(CURSOR_RULE)})

        assert plan(state).actions == ()
