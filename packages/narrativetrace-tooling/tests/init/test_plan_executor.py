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
    ReplaceLink,
)
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.plan_executor import execute_plan
from narrativetrace_tooling.init.report import Status

COORDINATE = "narrativetrace-skills==1.2.3"

AGENTS_MD = Path("AGENTS.md")
DOCTOR_PAGE = Path(".agents/skills/doctor/SKILL.md")
DOCTOR_DIRECTORY = Path(".agents/skills/doctor")
VENDOR_DOCTOR_PAGE = Path(".claude/skills/doctor/SKILL.md")

MISSING: Any = None


def make_plan(*actions: Action) -> InitPlan:
    return InitPlan(COORDINATE, False, actions)


def read(file: Path) -> str:
    return file.read_bytes().decode("utf-8")


def a_linked_vendor_directory(project: Path) -> Path:
    """What ``npx skills add`` leaves: the open-standard page for real, and the vendor path a link
    to the directory holding it. Returns the directory the link reaches."""
    reached = project / ".agents/skills/doctor"
    reached.mkdir(parents=True)
    (reached / "SKILL.md").write_bytes(b"open standard\n")
    (project / ".claude/skills").mkdir(parents=True)
    (project / ".claude/skills/doctor").symlink_to(reached)
    return reached


def replacing_the_vendor_link(target: str) -> InitPlan:
    return make_plan(
        ReplaceLink(Path(".claude/skills/doctor"), VENDOR_DOCTOR_PAGE, target, "vendor page\n")
    )


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


class TestReplacingALink:
    """The one action that begins by deleting: the link goes first — the link itself, never what it
    points at — so the write that follows creates a real path of the project's own."""

    def test_deletes_the_link_and_writes_a_real_file_where_it_was(self, tmp_path: Path) -> None:
        reached = a_linked_vendor_directory(tmp_path)
        link = tmp_path / ".claude/skills/doctor"

        report = execute_plan(replacing_the_vendor_link(str(reached)), tmp_path)

        assert not link.is_symlink()
        assert link.is_dir()
        assert read(tmp_path / VENDOR_DOCTOR_PAGE) == "vendor page\n"
        assert report.exit_code == 0

    def test_leaves_what_the_link_pointed_at_exactly_as_it_was(self, tmp_path: Path) -> None:
        """The whole point: after ``npx skills add`` the vendor path links to the OPEN-STANDARD
        page, and writing the vendor flavour through the link would destroy it."""
        reached = a_linked_vendor_directory(tmp_path)

        execute_plan(replacing_the_vendor_link(str(reached)), tmp_path)

        assert read(reached / "SKILL.md") == "open standard\n"

    def test_replaces_a_linked_page_inside_a_real_directory(self, tmp_path: Path) -> None:
        reached = tmp_path / ".agents/skills/doctor/SKILL.md"
        reached.parent.mkdir(parents=True)
        reached.write_bytes(b"open standard\n")
        (tmp_path / VENDOR_DOCTOR_PAGE).parent.mkdir(parents=True)
        (tmp_path / VENDOR_DOCTOR_PAGE).symlink_to(reached)

        execute_plan(
            make_plan(
                ReplaceLink(VENDOR_DOCTOR_PAGE, VENDOR_DOCTOR_PAGE, str(reached), "vendor page\n")
            ),
            tmp_path,
        )

        assert not (tmp_path / VENDOR_DOCTOR_PAGE).is_symlink()
        assert read(tmp_path / VENDOR_DOCTOR_PAGE) == "vendor page\n"
        assert read(reached) == "open standard\n"

    def test_refuses_when_the_link_itself_sits_behind_another_link(self, tmp_path: Path) -> None:
        """The executor guards the link's own ancestors before deleting it, so a link further up the
        path than the planner looked cannot turn a delete into a delete somewhere else."""
        elsewhere = tmp_path / "elsewhere"
        (elsewhere / "doctor").mkdir(parents=True)
        (elsewhere / "doctor/SKILL.md").write_bytes(b"theirs\n")
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude/skills").symlink_to(elsewhere)

        report = execute_plan(replacing_the_vendor_link("../x"), tmp_path)

        assert report.results[0].status is Status.REFUSED
        assert "symbolic link" in report.results[0].detail
        assert (elsewhere / "doctor").is_dir()
        assert read(elsewhere / "doctor/SKILL.md") == "theirs\n"

    def test_refuses_when_the_path_the_plan_called_a_link_is_a_real_directory(
        self, tmp_path: Path
    ) -> None:
        """The project changed under the plan. Deleting a real directory here would take whatever is
        in it, so the action is reported instead."""
        real = tmp_path / ".claude/skills/doctor"
        real.mkdir(parents=True)
        (real / "NOTES.md").write_bytes(b"mine\n")

        report = execute_plan(replacing_the_vendor_link("../x"), tmp_path)

        assert report.results[0].status is Status.REFUSED
        assert "no longer a symbolic link" in report.results[0].detail
        assert read(real / "NOTES.md") == "mine\n"

    def test_writes_the_page_when_the_link_has_already_gone(self, tmp_path: Path) -> None:
        """Somebody removed the link between the plan and the run. The plan's intent — a real page
        of the project's own at this path — is satisfied, so it is carried out, not refused."""
        (tmp_path / ".claude/skills").mkdir(parents=True)

        report = execute_plan(replacing_the_vendor_link("../../.agents/skills/doctor"), tmp_path)

        assert report.results[0].status is Status.APPLIED
        assert read(tmp_path / VENDOR_DOCTOR_PAGE) == "vendor page\n"

    def test_removes_a_directory_link_on_a_platform_that_will_not_unlink_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Windows needs ``rmdir`` for a link to a directory; POSIX needs ``unlink`` and raises
        ENOTDIR for ``rmdir``. Both are tried, so the one action that deletes works on either.

        The platform is SIMULATED — this container is POSIX and would never take the second branch —
        by making ``unlink`` refuse the way Windows does and ``rmdir`` do what Windows does. The
        assertions are still about the outcome: the link gone, the right page written, the target
        untouched.
        """
        reached = a_linked_vendor_directory(tmp_path)
        link = tmp_path / ".claude/skills/doctor"
        real_unlink = Path.unlink

        def windows_unlink(self: Path, missing_ok: bool = False) -> None:
            if self == link:
                raise OSError(13, "Permission denied")  # what Windows answers for a directory link
            real_unlink(self, missing_ok=missing_ok)

        def windows_rmdir(self: Path) -> None:
            real_unlink(self)  # what Windows' rmdir does to a directory link

        monkeypatch.setattr(Path, "unlink", windows_unlink)
        monkeypatch.setattr(Path, "rmdir", windows_rmdir)

        report = execute_plan(replacing_the_vendor_link(str(reached)), tmp_path)

        assert report.results[0].status is Status.APPLIED
        assert not link.is_symlink()
        assert read(tmp_path / VENDOR_DOCTOR_PAGE) == "vendor page\n"
        assert read(reached / "SKILL.md") == "open standard\n"


class TestTheExecutorsOwnPathGuard:
    """Rule 14, extended. The planners refuse every link they can see; this is the guarantee for one
    they cannot — a link made between the read and the write, or one further up the path than a
    planner looks. Not optional per the cross-port note: the executor carries its own guard rather
    than trusting the planner.
    """

    def test_refuses_to_write_through_a_linked_directory_on_the_way(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / f"{tmp_path.name}-outside"
        outside.mkdir()
        (tmp_path / ".agents").mkdir()
        (tmp_path / ".agents/skills").symlink_to(outside)

        report = execute_plan(make_plan(CreateFile(DOCTOR_PAGE, "page\n")), tmp_path)

        assert report.results[0].status is Status.REFUSED
        assert "symbolic link" in report.results[0].detail
        assert list(outside.iterdir()) == []

    def test_refuses_to_write_to_a_path_that_is_itself_a_link(self, tmp_path: Path) -> None:
        target = tmp_path / "somebodys-file.md"
        target.write_bytes(b"mine\n")
        (tmp_path / AGENTS_MD).symlink_to(target)

        report = execute_plan(make_plan(ReplaceBlock(AGENTS_MD, "old\n", "new\n")), tmp_path)

        assert report.results[0].status is Status.REFUSED
        assert read(target) == "mine\n"

    def test_refuses_to_delete_through_a_link_on_the_way(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / f"{tmp_path.name}-outside-delete"
        (outside / "doctor").mkdir(parents=True)
        (outside / "doctor/SKILL.md").write_bytes(b"theirs\n")
        (tmp_path / ".agents").mkdir()
        (tmp_path / ".agents/skills").symlink_to(outside)

        report = execute_plan(
            make_plan(
                DeleteFile(DOCTOR_PAGE, "theirs\n"), DeleteDirectory(Path(".agents/skills/doctor"))
            ),
            tmp_path,
        )

        assert {result.status for result in report.results} == {Status.REFUSED}
        assert read(outside / "doctor/SKILL.md") == "theirs\n"
        assert (outside / "doctor").is_dir()

    def test_refuses_to_delete_a_path_that_is_itself_a_link(self, tmp_path: Path) -> None:
        target = tmp_path / "somebodys-file.md"
        target.write_bytes(b"mine\n")
        (tmp_path / AGENTS_MD).symlink_to(target)

        report = execute_plan(make_plan(DeleteFile(AGENTS_MD, "mine\n")), tmp_path)

        assert report.results[0].status is Status.REFUSED
        assert (tmp_path / AGENTS_MD).is_symlink()
        assert read(target) == "mine\n"

    def test_the_rest_of_the_plan_still_runs_after_a_guarded_refusal(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / f"{tmp_path.name}-outside-rest"
        outside.mkdir()
        (tmp_path / ".agents").mkdir()
        (tmp_path / ".agents/skills").symlink_to(outside)

        report = execute_plan(
            make_plan(CreateFile(DOCTOR_PAGE, "page\n"), CreateFile(AGENTS_MD, "block\n")), tmp_path
        )

        assert report.results[0].status is Status.REFUSED
        assert report.results[1].status is Status.APPLIED
        assert read(tmp_path / AGENTS_MD) == "block\n"


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
