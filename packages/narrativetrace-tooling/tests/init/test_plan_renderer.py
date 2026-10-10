# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What a person and a script each see. The JSON envelope mirrors this runtime's own doctor, on
purpose: snake_case, two-space indent, one document.

Named after the Java port's ``PlanRendererTest`` so the two lists diff; it also carries that port's
``PlanRendererAdversarialM3Test`` case (the shared render decision every entry point makes).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from narrativetrace_tooling.init.action import (
    Action,
    AdoptPage,
    CreateFile,
    DeleteDirectory,
    DeleteFile,
    Refuse,
    ReplaceBlock,
    ReplaceLink,
)
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.plan_renderer import (
    render_diff,
    render_plan,
    render_plan_json,
    render_plan_text,
    render_report,
    render_report_json,
    render_report_text,
)
from narrativetrace_tooling.init.report import ExecutionReport, Status, applied, refused

COORDINATE = "narrativetrace-skills==1.2.3"

AGENTS_MD = Path("AGENTS.md")
DOCTOR_PAGE = Path(".agents/skills/doctor/SKILL.md")

MISSING: Any = None


def make_plan(*actions: Action) -> InitPlan:
    return InitPlan(COORDINATE, False, actions)


def create() -> Action:
    return CreateFile(AGENTS_MD, "# Agents\n")


def adopt() -> Action:
    return AdoptPage(
        DOCTOR_PAGE, "page\n", "<!-- installed by narrativetrace init from x -->\npage\n"
    )


def replace_link() -> Action:
    return ReplaceLink(
        Path(".claude/skills/doctor"),
        Path(".claude/skills/doctor/SKILL.md"),
        "../../.agents/skills/doctor",
        "vendor page\n",
    )


class TestText:
    def test_text_names_the_carrier_and_one_line_per_action(self) -> None:
        text = render_plan_text(
            make_plan(CreateFile(DOCTOR_PAGE, "page\n"), Refuse(AGENTS_MD, "two sections"))
        )

        assert COORDINATE in text
        assert "create  .agents/skills/doctor/SKILL.md" in text
        assert "refuse  AGENTS.md — two sections" in text
        assert "2 action(s), 1 refusal(s)" in text

    def test_text_says_so_when_there_is_nothing_to_do(self) -> None:
        assert "nothing to do" in render_plan_text(make_plan())

    def test_text_of_a_report_says_what_happened(self) -> None:
        report = ExecutionReport(
            COORDINATE,
            (
                applied(CreateFile(AGENTS_MD, "a\n")),
                refused(Refuse(Path("CLAUDE.md"), "x"), "no flag"),
            ),
        )

        text = render_report_text(report)

        assert "applied create  AGENTS.md" in text
        assert "refused refuse  CLAUDE.md — no flag" in text
        assert "1 applied, 1 refused" in text

    def test_a_kind_at_least_as_wide_as_the_column_still_keeps_one_space(self) -> None:
        """``delete-directory`` is wider than the column, so padding to it would run the kind into
        the path."""
        text = render_plan_text(make_plan(DeleteDirectory(Path(".agents/skills/doctor"))))

        assert "delete-directory .agents/skills/doctor" in text


class TestWhatARegistryTreeReadsLike:
    """Rule 17 says the plan, the diff and the report all say "adopted" rather than "replaced": a
    person has to be told that nothing of theirs was overwritten. A line that only a preview carries
    is a line the person who ran it for real never saw, so both texts say it.
    """

    def test_an_adoption_says_nothing_of_anybodys_was_overwritten(self) -> None:
        text = render_plan_text(make_plan(adopt()))

        assert (
            "adopt   .agents/skills/doctor/SKILL.md — adopted: identical to this carrier's page, so"
            " only the provenance line is added" in text
        )

    def test_the_report_says_it_too_and_not_only_the_preview(self) -> None:
        text = render_report_text(ExecutionReport(COORDINATE, (applied(adopt()),)))

        assert "applied adopt   .agents/skills/doctor/SKILL.md — adopted: identical" in text

    def test_replacing_a_link_names_the_link_and_what_it_pointed_at(self) -> None:
        text = render_plan_text(make_plan(replace_link()))

        assert (
            "replace-link .claude/skills/doctor/SKILL.md — replaces the symbolic link"
            " .claude/skills/doctor → ../../.agents/skills/doctor" in text
        )

    def test_the_report_names_the_replaced_link_as_well(self) -> None:
        text = render_report_text(ExecutionReport(COORDINATE, (applied(replace_link()),)))

        assert "applied replace-link .claude/skills/doctor/SKILL.md — replaces the symbolic" in text

    def test_a_filesystem_refusal_still_shows_its_own_detail_over_the_note(self) -> None:
        """The detail is what actually happened; the note is what was planned."""
        report = ExecutionReport(
            COORDINATE, (refused(replace_link(), "OSError: a link on the way"),)
        )

        assert "refused replace-link" in render_report_text(report)
        assert "OSError: a link on the way" in render_report_text(report)

    def test_an_ordinary_action_carries_no_note_at_all(self) -> None:
        """The whole line, not a substring: a note appended to every action would make "adopted"
        meaningless, and a mutation run surviving on ``else ""`` is what proved the fragment
        assertions elsewhere in this file could not see it."""
        text = render_plan_text(make_plan(CreateFile(DOCTOR_PAGE, "page\n")))

        assert text.splitlines()[-1] == "create  .agents/skills/doctor/SKILL.md"

    def test_an_adoption_diffs_as_the_one_line_it_adds_and_removes_nothing(self) -> None:
        """An adoption that showed a removal would be telling a person something of theirs went."""
        diff = render_diff(make_plan(adopt()))

        removed = [
            line
            for line in diff.splitlines()
            if line.startswith("-") and not line.startswith("---")
        ]
        assert "+<!-- installed by narrativetrace init from x -->" in diff
        assert removed == []

    def test_replacing_a_link_diffs_as_a_page_that_was_not_there(self) -> None:
        """``before`` is empty on purpose: what the link pointed at is left alone, and showing its
        text here would read as an edit to a file this action does not touch."""
        diff = render_diff(make_plan(replace_link()))

        assert "+vendor page" in diff
        assert "open standard" not in diff

    def test_both_new_kinds_reach_the_json_envelope_by_their_own_names(self) -> None:
        rows = json.loads(render_plan_json(make_plan(adopt(), replace_link())))["actions"]

        assert [row["kind"] for row in rows] == ["adopt", "replace-link"]
        assert [row["path"] for row in rows] == [
            ".agents/skills/doctor/SKILL.md",
            ".claude/skills/doctor/SKILL.md",
        ]
        assert {row["status"] for row in rows} == {"planned"}


class TestJson:
    def test_json_of_a_plan_is_the_doctors_envelope_with_planned_actions(self) -> None:
        json_text = render_plan_json(
            make_plan(CreateFile(DOCTOR_PAGE, "page\n"), Refuse(AGENTS_MD, "two sections"))
        )

        assert json.loads(json_text) == {
            "carrier": COORDINATE,
            "actions": [
                {
                    "kind": "create",
                    "path": ".agents/skills/doctor/SKILL.md",
                    "status": "planned",
                },
                {"kind": "refuse", "path": "AGENTS.md", "status": "refused"},
            ],
            "exit_code": 1,
        }

    def test_json_is_snake_case_and_two_space_indented_like_the_doctors(self) -> None:
        json_text = render_plan_json(make_plan(create()))

        assert json_text.startswith('{\n  "carrier": ')
        assert json_text.endswith('"exit_code": 0\n}')
        assert "exitCode" not in json_text

    def test_json_of_an_empty_plan_still_carries_the_envelope(self) -> None:
        assert json.loads(render_plan_json(make_plan())) == {
            "carrier": COORDINATE,
            "actions": [],
            "exit_code": 0,
        }

    def test_json_of_a_dry_run_exits_zero(self) -> None:
        dry = InitPlan(COORDINATE, True, (Refuse(Path("A.md"), "x"),))

        assert json.loads(render_plan_json(dry))["exit_code"] == 0

    def test_json_of_a_report_carries_what_happened(self) -> None:
        report = ExecutionReport(COORDINATE, (applied(CreateFile(AGENTS_MD, "a\n")),))

        payload = json.loads(render_report_json(report))

        assert payload["actions"][0]["status"] == "applied"
        assert payload["exit_code"] == 0

    def test_json_of_a_report_is_the_same_envelope_row_for_row(self) -> None:
        report = ExecutionReport(
            COORDINATE,
            (
                applied(CreateFile(AGENTS_MD, "a\n")),
                refused(Refuse(Path("CLAUDE.md"), "x"), "no flag"),
            ),
        )

        assert json.loads(render_report_json(report)) == {
            "carrier": COORDINATE,
            "actions": [
                {"kind": "create", "path": "AGENTS.md", "status": "applied"},
                {"kind": "refuse", "path": "CLAUDE.md", "status": "refused"},
            ],
            "exit_code": 1,
        }

    @pytest.mark.parametrize(
        "name", ["ab.md", "my notes.md", '.agents/sk"ill\\x/SKILL.md', "año.md"]
    )
    def test_json_survives_whatever_ends_up_in_a_path(self, name: str) -> None:
        """A control character, a space (0x20, the first character that must NOT be escaped), a
        quote, a backslash and a non-ASCII letter — all of them read back as the path that went
        in."""
        json_text = render_plan_json(make_plan(CreateFile(Path(name), "x")))

        assert json.loads(json_text)["actions"][0]["path"] == name

    def test_json_escapes_a_control_character_rather_than_emitting_it_raw(self) -> None:
        json_text = render_plan_json(make_plan(CreateFile(Path("ab.md"), "x")))

        assert '"path": "a\\u0001b.md"' in json_text
        assert json.loads(json_text)["actions"][0]["path"] == "ab.md"


class TestDiff:
    def test_diff_of_a_created_file_comes_from_nowhere(self) -> None:
        diff = render_diff(make_plan(CreateFile(AGENTS_MD, "a\nb\n")))

        assert diff == "--- /dev/null\n+++ b/AGENTS.md\n@@ -0,0 +1,2 @@\n+a\n+b\n"

    def test_diff_of_a_deleted_file_goes_nowhere(self) -> None:
        diff = render_diff(make_plan(DeleteFile(AGENTS_MD, "a\n")))

        assert diff == "--- a/AGENTS.md\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-a\n"

    def test_diff_of_a_replacement_shows_only_what_changed_with_context(self) -> None:
        before = "1\n2\n3\n4\n5\nold\n6\n7\n8\n9\n"
        after = "1\n2\n3\n4\n5\nnew\n6\n7\n8\n9\n"

        diff = render_diff(make_plan(ReplaceBlock(Path("A.md"), before, after)))

        assert diff == (
            "--- a/A.md\n+++ b/A.md\n@@ -3,7 +3,7 @@\n 3\n 4\n 5\n-old\n+new\n 6\n 7\n 8\n"
        )

    def test_diff_marks_a_missing_final_newline_on_both_sides(self) -> None:
        diff = render_diff(make_plan(ReplaceBlock(Path("A.md"), "a", "b")))

        assert diff == (
            "--- a/A.md\n+++ b/A.md\n@@ -1,1 +1,1 @@\n"
            "-a\n\\ No newline at end of file\n"
            "+b\n\\ No newline at end of file\n"
        )

    def test_diff_shows_a_line_ending_change_rather_than_nothing(self) -> None:
        diff = render_diff(make_plan(ReplaceBlock(Path("A.md"), "a\n", "a\r\n")))

        assert "-a\n" in diff
        assert "+a\r\n" in diff

    def test_diff_describes_the_actions_that_have_no_content(self) -> None:
        diff = render_diff(
            make_plan(
                DeleteDirectory(Path(".agents/skills/doctor")), Refuse(AGENTS_MD, "two sections")
            )
        )

        assert diff == (
            "# .agents/skills/doctor — delete-directory\n# AGENTS.md — refused: two sections\n"
        )

    def test_diff_of_a_line_inserted_beside_its_twin_counts_each_side_once(self) -> None:
        """An inserted line identical to its neighbour: the suffix scan must stop where the prefix
        did."""
        diff = render_diff(make_plan(ReplaceBlock(Path("A.md"), "a\n", "a\na\n")))

        assert diff == "--- a/A.md\n+++ b/A.md\n@@ -1,1 +1,2 @@\n a\n+a\n"

    def test_diff_of_a_line_removed_beside_its_twin_counts_each_side_once(self) -> None:
        """The mirror of the case above: a REMOVED line identical to its neighbour."""
        diff = render_diff(make_plan(ReplaceBlock(Path("A.md"), "a\na\n", "a\n")))

        assert diff == "--- a/A.md\n+++ b/A.md\n@@ -1,2 +1,1 @@\n a\n-a\n"

    def test_diff_of_an_unchanged_file_is_empty(self) -> None:
        assert render_diff(make_plan(ReplaceBlock(Path("A.md"), "a\n", "a\n"))) == ""


class TestTheOneDecisionEveryEntryPointShares:
    def test_a_plan_renders_as_the_summary_and_the_diff_together(self) -> None:
        plan = InitPlan(COORDINATE, True, (create(),))

        assert render_plan(plan, as_json=False) == render_plan_text(plan) + render_diff(plan)

    def test_a_plan_renders_as_nothing_but_the_envelope_when_json_is_asked(self) -> None:
        plan = InitPlan(COORDINATE, True, (create(),))

        assert render_plan(plan, as_json=True) == render_plan_json(plan)

    def test_an_applied_run_renders_as_its_own_summary_or_its_own_envelope(self) -> None:
        report = ExecutionReport(COORDINATE, (applied(create()),))

        assert render_report(report, as_json=False) == render_report_text(report)
        assert render_report(report, as_json=True) == render_report_json(report)


class TestGuards:
    def test_refuses_to_render_nothing(self) -> None:
        for render in (
            render_plan_text,
            render_plan_json,
            render_diff,
            render_report_text,
            render_report_json,
        ):
            with pytest.raises(TypeError, match=r"there is nothing to render"):
                render(MISSING)

    def test_a_status_that_is_not_applied_reads_as_refused(self) -> None:
        """The report's own guards make any other status impossible, so this pins the mapping rather
        than a branch: exactly two statuses, exactly two tokens."""
        assert {Status.APPLIED, Status.REFUSED} == set(Status)
