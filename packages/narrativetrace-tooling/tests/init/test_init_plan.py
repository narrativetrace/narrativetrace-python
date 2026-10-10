# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A plan is the whole of what an install would do, computed before anything is written. These cases
pin what an action promises the executor — a complete before and after, never a path outside the
project — and what a plan promises a reader: one action per path, and a refusal that says why.

Named after the Java port's ``InitPlanTest`` so the two lists diff; it also carries that port's
``ExecutionReportAdversarialM3Test`` cases, since the report is the same promise on the other side.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from narrativetrace_tooling.init import plan as plan_module
from narrativetrace_tooling.init.action import (
    Action,
    AdoptPage,
    AppendBlock,
    AppendLine,
    CreateFile,
    DeleteDirectory,
    DeleteFile,
    Refuse,
    ReplaceBlock,
    ReplaceLink,
)
from narrativetrace_tooling.init.options import InitOptions, Scope, Vendor
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.report import (
    Applied,
    ExecutionReport,
    Status,
    applied,
    refused,
)

COORDINATE = "narrativetrace-skills==1.2.3"

AGENTS_MD = Path("AGENTS.md")

MISSING: Any = None


def make_plan(*actions: Action) -> InitPlan:
    return InitPlan(COORDINATE, False, actions)


@pytest.fixture
def subject() -> Iterator[InitPlan]:
    """The invariant is checked around every case: a test that reached past the frozen value and
    corrupted it should fail in the test that did it, not in the next one."""
    plan = make_plan(CreateFile(AGENTS_MD, "block\n"))
    assert plan_module._invariant(plan), "the plan is inconsistent before the test"
    yield plan
    assert plan_module._invariant(plan), "the test left the plan inconsistent"


class TestWhatEachActionPromises:
    def test_a_created_file_has_no_before(self) -> None:
        action = CreateFile(AGENTS_MD, "block\n")

        assert action.before == ""
        assert action.after == "block\n"
        assert action.kind == "create"

    def test_a_replacement_carries_both_whole_file_texts(self) -> None:
        action = ReplaceBlock(AGENTS_MD, "old\n", "new\n")

        assert action.before == "old\n"
        assert action.after == "new\n"
        assert action.kind == "replace"

    def test_an_append_computes_its_after_from_what_was_there(self) -> None:
        action = AppendBlock(AGENTS_MD, "# Title\n", "block\n")

        assert action.after == "# Title\n\nblock\n"
        assert action.kind == "append"

    def test_an_appended_line_ends_with_the_files_own_line_ending(self) -> None:
        unix = AppendLine(Path("CLAUDE.md"), "# C\n", "@AGENTS.md")
        windows = AppendLine(Path("CLAUDE.md"), "# C\r\n", "@AGENTS.md")

        assert unix.after == "# C\n\n@AGENTS.md\n"
        assert windows.after == "# C\r\n\r\n@AGENTS.md\r\n"
        assert unix.kind == "append-line"

    def test_a_deletion_ends_with_nothing(self) -> None:
        file = DeleteFile(AGENTS_MD, "gone\n")
        directory = DeleteDirectory(Path(".agents/skills/doctor"))

        assert file.after == ""
        assert file.before == "gone\n"
        assert file.kind == "delete"
        assert directory.kind == "delete-directory"

    def test_a_refusal_carries_its_reason(self) -> None:
        refusal = Refuse(AGENTS_MD, "two blocks")

        assert refusal.reason == "two blocks"
        assert refusal.kind == "refuse"

    def test_an_adoption_is_its_own_kind_and_not_a_replacement(self) -> None:
        """A separate kind from ``replace`` so that the plan, the diff and the report all say
        "adopted": a person has to be told that nothing of theirs was overwritten, which is also why
        adoption needs no ``--force``."""
        action = AdoptPage(Path(".agents/skills/doctor/SKILL.md"), "page\n", "stamped\npage\n")

        assert action.before == "page\n"
        assert action.after == "stamped\npage\n"
        assert action.kind == "adopt"

    def test_refuses_an_adoption_where_there_is_no_page_to_adopt(self) -> None:
        with pytest.raises(ValueError, match=r"nothing to adopt where there is no page"):
            AdoptPage(AGENTS_MD, "", "stamped\n")

    def test_replacing_a_link_is_keyed_on_the_page_and_carries_no_before(self) -> None:
        """``before`` is empty on purpose: the link is deleted first, so nothing this PATH used to
        reach survives here — and what it pointed at is left exactly as it was, which is the whole
        point. A diff showing the other flavour's text here would read as an edit to somebody's
        file."""
        action = ReplaceLink(
            Path(".claude/skills/doctor"),
            Path(".claude/skills/doctor/SKILL.md"),
            "../../.agents/skills/doctor",
            "vendor page\n",
        )

        assert action.path == Path(".claude/skills/doctor/SKILL.md")
        assert action.link == Path(".claude/skills/doctor")
        assert action.target == "../../.agents/skills/doctor"
        assert action.before == ""
        assert action.after == "vendor page\n"
        assert action.kind == "replace-link"

    def test_the_link_may_be_the_page_itself(self) -> None:
        page = Path(".claude/skills/doctor/SKILL.md")

        action = ReplaceLink(page, page, "../other/SKILL.md", "vendor page\n")

        assert action.path == page
        assert action.link == page

    def test_refuses_to_replace_a_link_without_saying_what_it_pointed_at(self) -> None:
        with pytest.raises(ValueError, match=r"replacing a link names what it pointed at"):
            ReplaceLink(Path(".claude/skills/d"), Path(".claude/skills/d/SKILL.md"), " ", "page\n")

    def test_refuses_to_replace_a_link_with_an_empty_file(self) -> None:
        with pytest.raises(ValueError, match=r"replaced by a page, never by an empty file"):
            ReplaceLink(Path(".claude/skills/d"), Path(".claude/skills/d/SKILL.md"), "../x", "")

    def test_refuses_a_page_that_is_not_behind_the_link_being_replaced(self) -> None:
        """Otherwise the plan would delete one path and write another, and the diff would describe
        neither."""
        with pytest.raises(ValueError, match=r"is not behind the link"):
            ReplaceLink(
                Path(".claude/skills/doctor"),
                Path(".agents/skills/doctor/SKILL.md"),
                "../x",
                "page\n",
            )

    def test_every_kind_is_its_own_stable_token(self) -> None:
        """The kind is what a JSON envelope and a text summary both print, so two actions sharing
        one would make a report ambiguous to whatever reads it."""
        kinds = [
            CreateFile(AGENTS_MD, "x").kind,
            ReplaceBlock(AGENTS_MD, "a", "b").kind,
            AdoptPage(AGENTS_MD, "a", "b").kind,
            AppendBlock(AGENTS_MD, "a", "b").kind,
            AppendLine(AGENTS_MD, "a", "b").kind,
            DeleteFile(AGENTS_MD, "a").kind,
            DeleteDirectory(AGENTS_MD).kind,
            Refuse(AGENTS_MD, "why").kind,
            ReplaceLink(Path("d"), Path("d/SKILL.md"), "../x", "page\n").kind,
        ]

        assert sorted(kinds) == sorted(set(kinds))
        assert len(kinds) == 9


class TestWhereAnActionMayPoint:
    @pytest.mark.parametrize(
        "outside", ["/etc/passwd", "../outside.md", ".agents/../../x", "", "."]
    )
    def test_refuses_an_action_on_a_path_outside_the_project(self, outside: str) -> None:
        with pytest.raises(ValueError, match=r"project-relative"):
            CreateFile(Path(outside), "x")

    def test_normalises_a_path_that_stays_inside(self) -> None:
        assert CreateFile(Path(".agents/skills/../skills/d/SKILL.md"), "x").path == Path(
            ".agents/skills/d/SKILL.md"
        )

    def test_refuses_a_directory_action_on_a_path_outside_the_project(self) -> None:
        with pytest.raises(ValueError, match=r"project-relative"):
            DeleteDirectory(Path(".agents/../../x"))

    def test_refuses_a_refusal_without_a_reason(self) -> None:
        with pytest.raises(ValueError, match=r"reason"):
            Refuse(AGENTS_MD, " ")

    def test_refuses_an_action_without_a_path_or_content(self) -> None:
        with pytest.raises(TypeError, match=r"path"):
            CreateFile(MISSING, "x")
        with pytest.raises(TypeError, match=r"text"):
            CreateFile(AGENTS_MD, MISSING)
        with pytest.raises(TypeError, match=r"text"):
            ReplaceBlock(AGENTS_MD, "a", MISSING)


class TestWhatAPlanPromises:
    def test_an_empty_plan_is_what_a_nothing_to_do_run_looks_like(self) -> None:
        empty = make_plan()

        assert empty.is_empty is True
        assert empty.has_refusals is False
        assert empty.exit_code == 0
        assert plan_module._invariant(empty) is True

    def test_a_refusal_makes_the_run_exit_one(self) -> None:
        plan = make_plan(Refuse(AGENTS_MD, "two blocks"))

        assert plan.has_refusals is True
        assert len(plan.refusals) == 1
        assert plan.exit_code == 1

    def test_a_dry_run_always_exits_zero_even_with_a_refusal(self) -> None:
        dry = InitPlan(COORDINATE, True, (Refuse(AGENTS_MD, "no"),))

        assert dry.dry_run is True
        assert dry.has_refusals is True
        assert dry.exit_code == 0

    def test_refuses_two_actions_on_one_path(self) -> None:
        with pytest.raises(AssertionError):
            make_plan(CreateFile(AGENTS_MD, "a"), ReplaceBlock(AGENTS_MD, "a", "b"))

    def test_refuses_a_plan_without_a_carrier(self) -> None:
        with pytest.raises(ValueError, match=r"carrier"):
            InitPlan(" ", False, ())
        with pytest.raises(TypeError, match=r"actions"):
            InitPlan(COORDINATE, False, MISSING)

    def test_keeps_its_actions_as_a_tuple_nothing_can_append_to(self, subject: InitPlan) -> None:
        assert isinstance(subject.actions, tuple)

    def test_reads_back_every_refusal_in_plan_order(self) -> None:
        plan = make_plan(
            Refuse(AGENTS_MD, "first"),
            CreateFile(Path("NOTES.md"), "x"),
            Refuse(Path("CLAUDE.md"), "second"),
        )

        assert [refusal.reason for refusal in plan.refusals] == ["first", "second"]


class TestOptions:
    def test_the_default_options_write_nothing_it_was_not_asked_to(self) -> None:
        options = InitOptions()

        assert options.dry_run is False
        assert options.write_existing is False
        assert options.force is False
        assert options.scope is Scope.BOTH
        assert options.vendor_claude is Vendor.AUTO

    def test_each_scope_knows_what_it_covers(self) -> None:
        assert Scope.BOTH.includes_skills is True
        assert Scope.BOTH.includes_agents_md is True
        assert Scope.SKILLS.includes_skills is True
        assert Scope.SKILLS.includes_agents_md is False
        assert Scope.AGENTS_MD.includes_skills is False
        assert Scope.AGENTS_MD.includes_agents_md is True

    def test_changes_one_option_at_a_time(self) -> None:
        options = dataclasses.replace(
            InitOptions(),
            dry_run=True,
            write_existing=True,
            force=True,
            scope=Scope.SKILLS,
            vendor_claude=Vendor.OFF,
        )

        assert options.dry_run is True
        assert options.write_existing is True
        assert options.force is True
        assert options.scope is Scope.SKILLS
        assert options.vendor_claude is Vendor.OFF

    def test_refuses_options_without_a_scope_or_a_vendor_rule(self) -> None:
        with pytest.raises(TypeError, match=r"scope"):
            InitOptions(scope=MISSING)
        with pytest.raises(TypeError, match=r"vendor"):
            InitOptions(vendor_claude=MISSING)


class TestWhatAReportPromises:
    """The same contract a planned refusal holds, held where a refusal is RECORDED rather than
    planned: a refusal nobody can act on is worse than no refusal at all — it reaches a person as an
    empty parenthesis in a warning."""

    def test_refuses_to_record_a_refusal_that_carries_no_reason(self) -> None:
        action = CreateFile(AGENTS_MD, "# Agents\n")

        with pytest.raises(ValueError, match=r"reason"):
            Applied(action, Status.REFUSED, "   ")
        with pytest.raises(ValueError, match=r"reason"):
            Applied(action, Status.REFUSED, "")

    def test_an_applied_result_needs_no_detail(self) -> None:
        result = applied(CreateFile(AGENTS_MD, "# Agents\n"))

        assert result.detail == ""
        assert result.status is Status.APPLIED

    def test_a_recorded_refusal_carries_what_it_refused(self) -> None:
        result = refused(CreateFile(AGENTS_MD, "x"), "no flag")

        assert result.status is Status.REFUSED
        assert result.detail == "no flag"

    def test_a_report_exits_one_when_anything_was_refused(self) -> None:
        action = CreateFile(AGENTS_MD, "x")
        clean = ExecutionReport(COORDINATE, (applied(action),))
        mixed = ExecutionReport(COORDINATE, (applied(action), refused(action, "why")))

        assert clean.has_refusals is False
        assert clean.exit_code == 0
        assert mixed.has_refusals is True
        assert mixed.exit_code == 1

    def test_refuses_a_report_without_a_carrier_or_results(self) -> None:
        with pytest.raises(ValueError, match=r"carrier"):
            ExecutionReport(" ", ())
        with pytest.raises(TypeError, match=r"results"):
            ExecutionReport(COORDINATE, MISSING)

    def test_refuses_a_result_missing_its_action_or_status(self) -> None:
        with pytest.raises(TypeError, match=r"action"):
            Applied(MISSING, Status.APPLIED, "")
        with pytest.raises(TypeError, match=r"status"):
            Applied(CreateFile(AGENTS_MD, "x"), MISSING, "")
        with pytest.raises(TypeError, match=r"detail"):
            Applied(CreateFile(AGENTS_MD, "x"), Status.APPLIED, MISSING)
