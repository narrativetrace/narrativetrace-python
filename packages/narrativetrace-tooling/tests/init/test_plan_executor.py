# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The only module in the installer that writes. Everything here happens on a real temp directory.

Named after the Java port's ``PlanExecutorTest`` so the two lists diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from narrativetrace_tooling.init.action import (
    Action,
    AppendBlock,
    CreateFile,
    DeleteDirectory,
    DeleteFile,
    Refuse,
    ReplaceBlock,
)
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.plan_executor import execute_plan
from narrativetrace_tooling.init.report import Status

COORDINATE = "narrativetrace-skills==1.2.3"

AGENTS_MD = Path("AGENTS.md")
DOCTOR_PAGE = Path(".agents/skills/doctor/SKILL.md")
DOCTOR_DIRECTORY = Path(".agents/skills/doctor")

MISSING: Any = None


def make_plan(*actions: Action) -> InitPlan:
    return InitPlan(COORDINATE, False, actions)


def read(file: Path) -> str:
    return file.read_bytes().decode("utf-8")


class TestWriting:
    def test_creates_a_file_and_every_directory_above_it(self, tmp_path: Path) -> None:
        report = execute_plan(make_plan(CreateFile(DOCTOR_PAGE, "page\n")), tmp_path)

        assert read(tmp_path / DOCTOR_PAGE) == "page\n"
        assert report.exit_code == 0
        assert [result.status for result in report.results] == [Status.APPLIED]

    def test_writes_exactly_the_bytes_the_plan_carries(self, tmp_path: Path) -> None:
        """A byte-order mark, CRLF terminators and no final newline all survive: the plan's text IS
        the file, and a newline translated on the way out would rewrite a file nobody asked to
        rewrite."""
        windows = "﻿# Agents\r\n\r\nblock\r\n\r\nno final newline"

        execute_plan(make_plan(CreateFile(AGENTS_MD, windows)), tmp_path)

        assert read(tmp_path / AGENTS_MD) == windows

    def test_replaces_an_existing_file(self, tmp_path: Path) -> None:
        (tmp_path / AGENTS_MD).write_bytes(b"old\n")

        execute_plan(make_plan(ReplaceBlock(AGENTS_MD, "old\n", "new\n")), tmp_path)

        assert read(tmp_path / AGENTS_MD) == "new\n"

    def test_applies_what_the_action_computed_not_what_is_on_disk(self, tmp_path: Path) -> None:
        (tmp_path / AGENTS_MD).write_bytes(b"# Agents\n")

        execute_plan(make_plan(AppendBlock(AGENTS_MD, "# Agents\n", "block\n")), tmp_path)

        assert read(tmp_path / AGENTS_MD) == "# Agents\n\nblock\n"

    def test_leaves_no_temporary_file_behind(self, tmp_path: Path) -> None:
        execute_plan(
            make_plan(CreateFile(AGENTS_MD, "a\n"), CreateFile(Path("CLAUDE.md"), "b\n")), tmp_path
        )

        assert sorted(path.name for path in tmp_path.iterdir()) == ["AGENTS.md", "CLAUDE.md"]


class TestDeleting:
    def test_deletes_a_file_and_then_its_directory(self, tmp_path: Path) -> None:
        page = tmp_path / DOCTOR_PAGE
        page.parent.mkdir(parents=True)
        page.write_bytes(b"page\n")

        report = execute_plan(
            make_plan(DeleteFile(DOCTOR_PAGE, "page\n"), DeleteDirectory(DOCTOR_DIRECTORY)),
            tmp_path,
        )

        assert not page.exists()
        assert not page.parent.exists()
        assert report.exit_code == 0

    def test_deleting_something_already_gone_is_still_applied(self, tmp_path: Path) -> None:
        report = execute_plan(
            make_plan(DeleteFile(AGENTS_MD, "gone\n"), DeleteDirectory(DOCTOR_DIRECTORY)), tmp_path
        )

        assert report.exit_code == 0
        assert {result.status for result in report.results} == {Status.APPLIED}

    def test_leaves_a_directory_that_still_holds_somebody_elses_file_and_says_so(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / DOCTOR_DIRECTORY
        directory.mkdir(parents=True)
        (directory / "NOTES.md").write_bytes(b"mine\n")

        report = execute_plan(make_plan(DeleteDirectory(DOCTOR_DIRECTORY)), tmp_path)

        assert directory.exists()
        assert (directory / "NOTES.md").exists()
        assert report.exit_code == 1
        assert "not empty" in report.results[0].detail

    def test_reports_a_path_that_is_not_a_directory_rather_than_deleting_it(
        self, tmp_path: Path
    ) -> None:
        """The planners only ever name a directory of ours here, so anything else means the project
        changed under the plan — and taking somebody's file with it would be the worst answer."""
        (tmp_path / ".agents").mkdir()
        (tmp_path / ".agents/skills").mkdir()
        (tmp_path / DOCTOR_DIRECTORY).write_bytes(b"a file, not a directory\n")

        report = execute_plan(make_plan(DeleteDirectory(DOCTOR_DIRECTORY)), tmp_path)

        assert (tmp_path / DOCTOR_DIRECTORY).is_file()
        assert report.results[0].status is Status.REFUSED


class TestWhenSomethingWillNotCooperate:
    def test_reports_a_refusal_and_writes_nothing_for_it(self, tmp_path: Path) -> None:
        report = execute_plan(make_plan(Refuse(AGENTS_MD, "two sections")), tmp_path)

        assert not (tmp_path / AGENTS_MD).exists()
        assert report.results[0].status is Status.REFUSED
        assert report.results[0].detail == "two sections"
        assert report.exit_code == 1

    def test_a_failed_write_leaves_what_was_there_intact_and_the_rest_of_the_plan_runs(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / AGENTS_MD).mkdir()
        (tmp_path / AGENTS_MD / "inside.txt").write_bytes(b"untouched\n")

        report = execute_plan(
            make_plan(
                ReplaceBlock(AGENTS_MD, "old\n", "new\n"), CreateFile(Path("NOTES.md"), "written\n")
            ),
            tmp_path,
        )

        assert read(tmp_path / AGENTS_MD / "inside.txt") == "untouched\n"
        assert read(tmp_path / "NOTES.md") == "written\n"
        assert report.results[0].status is Status.REFUSED
        assert report.results[1].status is Status.APPLIED
        assert report.exit_code == 1

    def test_a_failed_write_leaves_no_temporary_file_behind_either(self, tmp_path: Path) -> None:
        (tmp_path / AGENTS_MD).mkdir()
        (tmp_path / AGENTS_MD / "inside.txt").write_bytes(b"untouched\n")

        execute_plan(make_plan(ReplaceBlock(AGENTS_MD, "old\n", "new\n")), tmp_path)

        assert sorted(path.name for path in tmp_path.iterdir()) == ["AGENTS.md"]

    def test_names_the_failure_in_the_refusal_so_a_person_can_act_on_it(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / AGENTS_MD).mkdir()

        report = execute_plan(make_plan(ReplaceBlock(AGENTS_MD, "old\n", "new\n")), tmp_path)

        assert report.results[0].detail.strip() != ""
        assert "Error" in report.results[0].detail


class TestTheReport:
    def test_reports_the_carrier_and_every_action_in_plan_order(self, tmp_path: Path) -> None:
        report = execute_plan(
            make_plan(CreateFile(AGENTS_MD, "a\n"), Refuse(Path("CLAUDE.md"), "no flag")), tmp_path
        )

        assert report.carrier == COORDINATE
        assert [str(result.action.path) for result in report.results] == ["AGENTS.md", "CLAUDE.md"]
        assert report.has_refusals is True

    def test_an_empty_plan_applies_cleanly(self, tmp_path: Path) -> None:
        report = execute_plan(make_plan(), tmp_path)

        assert report.results == ()
        assert report.exit_code == 0
        assert report.has_refusals is False


class TestGuards:
    def test_refuses_to_apply_a_dry_run_plan(self, tmp_path: Path) -> None:
        dry = InitPlan(COORDINATE, True, ())

        with pytest.raises(ValueError, match=r"a dry run is shown, never applied"):
            execute_plan(dry, tmp_path)

    def test_refuses_to_apply_to_something_that_is_not_a_directory(self, tmp_path: Path) -> None:
        file = tmp_path / "a-file"
        file.write_bytes(b"x")

        with pytest.raises(ValueError, match=r"is not a directory"):
            execute_plan(make_plan(), file)

    def test_refuses_to_apply_nothing_or_apply_nowhere(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError, match=r"the plan and a project directory"):
            execute_plan(MISSING, tmp_path)
        with pytest.raises(TypeError, match=r"the plan and a project directory"):
            execute_plan(make_plan(), MISSING)
