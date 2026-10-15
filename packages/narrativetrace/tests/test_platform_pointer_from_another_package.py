# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The platform pointers as an ENTRY POINT sees them (Phase 8, platform pointers): the real
carrier, a real directory, only what ``narrativetrace_tooling.init`` re-exports.

Named after the Java port's ``PlatformPointerFromAnotherPackageTest`` so the two lists diff; also
carries the adversarial cases Java's pass found (a byte-order mark on line 1, a near-miss marker, a
link) and the mixed case of two markers at once.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from narrativetrace_tooling.init import (
    Carrier,
    ExecutionReport,
    InitOptions,
    PointerReading,
    execute_plan,
    plan_init,
    plan_uninstall,
    read_pointer_readings,
    read_project_state,
    resolve_carrier,
)

RULE = ".cursor/rules/narrativetrace.mdc"
BOM = "﻿"


@pytest.fixture(scope="session")
def carrier() -> Carrier:
    return resolve_carrier()


def install(project: Path, carrier: Carrier, options: InitOptions | None = None) -> ExecutionReport:
    plan = plan_init(read_project_state(project), carrier, options or InitOptions())
    return execute_plan(plan, project)


def uninstall(project: Path) -> ExecutionReport:
    return execute_plan(plan_uninstall(read_project_state(project), InitOptions()), project)


def write(project: Path, relative: str, content: str) -> None:
    file = project / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content.encode("utf-8"))


def read(project: Path, relative: str) -> str:
    return (project / relative).read_bytes().decode("utf-8")


def tree(project: Path) -> dict[str, bytes]:
    return {
        str(file.relative_to(project)): file.read_bytes()
        for file in sorted(project.rglob("*"))
        if file.is_file() and not file.is_symlink()
    }


class TestTheRealInstall:
    def test_writes_the_cursor_rule_stamped_with_the_carrier(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".cursor").mkdir()

        assert install(tmp_path, carrier).exit_code == 0

        rule = read(tmp_path, RULE)
        assert rule.startswith("---\n")
        assert f"<!-- narrativetrace:start {carrier.coordinate} -->" in rule
        assert ".agents/skills" in rule

    def test_a_replit_file_makes_a_stamped_replit_md_with_the_created_note(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        write(tmp_path, ".replit", "run = 'python main.py'\n")

        install(tmp_path, carrier)

        text = read(tmp_path, "replit.md")
        assert text.startswith("<!-- narrativetrace:created -->\n")
        assert f"<!-- narrativetrace:start {carrier.coordinate} -->" in text

    def test_a_project_on_no_platform_gets_neither_pointer(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        install(tmp_path, carrier)

        assert not (tmp_path / "replit.md").exists()
        assert not (tmp_path / ".cursor").exists()

    def test_a_near_miss_marker_gets_no_pointer(self, carrier: Carrier, tmp_path: Path) -> None:
        (tmp_path / ".cursorx").mkdir()
        (tmp_path / ".replitx").mkdir()

        install(tmp_path, carrier)

        assert not (tmp_path / ".cursor").exists()
        assert not (tmp_path / "replit.md").exists()

    def test_a_second_install_plans_nothing(self, carrier: Carrier, tmp_path: Path) -> None:
        (tmp_path / ".cursor").mkdir()
        write(tmp_path, ".replit", "")
        install(tmp_path, carrier)

        assert plan_init(read_project_state(tmp_path), carrier, InitOptions()).is_empty

    def test_both_markers_at_once_write_both_pointers_and_uninstall_removes_exactly_them(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".cursor").mkdir()
        write(tmp_path, "replit.md", "# Notes\n")
        before = tree(tmp_path)

        install(tmp_path, carrier, InitOptions(write_existing=True))
        assert (tmp_path / RULE).is_file()
        assert read(tmp_path, "replit.md").startswith("# Notes\n\n<!-- narrativetrace:start")

        uninstall(tmp_path)

        assert tree(tmp_path) == before
        assert (tmp_path / ".cursor").is_dir(), "the user's directory is never removed"


class TestRoundTripsKeepTheUsersBytes:
    @pytest.mark.parametrize("eol", ["\n", "\r\n"])
    def test_install_then_uninstall_leaves_a_replit_md_byte_identical(
        self, carrier: Carrier, tmp_path: Path, eol: str
    ) -> None:
        original = f"# Notes{eol}{eol}keep me{eol}"
        write(tmp_path, "replit.md", original)

        install(tmp_path, carrier, InitOptions(write_existing=True))
        uninstall(tmp_path)

        assert read(tmp_path, "replit.md") == original

    def test_a_byte_order_mark_replit_md_comes_back_identical(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        original = BOM + "# Notes\n"
        write(tmp_path, "replit.md", original)

        install(tmp_path, carrier, InitOptions(write_existing=True))
        uninstall(tmp_path)

        assert read(tmp_path, "replit.md") == original

    def test_a_section_after_a_byte_order_mark_is_refreshed_and_the_mark_survives(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".replit").write_text("")
        install(tmp_path, carrier)
        current = read(tmp_path, "replit.md")
        stale = BOM + current.replace(carrier.coordinate, "narrativetrace-skills==0.0.1")
        write(tmp_path, "replit.md", stale)

        install(tmp_path, carrier)

        assert read(tmp_path, "replit.md") == BOM + current

    def test_a_byte_order_mark_on_a_rule_the_installer_made_still_deletes_it(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".cursor").mkdir()
        install(tmp_path, carrier)
        write(tmp_path, RULE, BOM + read(tmp_path, RULE))

        uninstall(tmp_path)

        assert not (tmp_path / RULE).exists()

    def test_a_crlf_rule_that_is_current_is_not_rewritten_and_is_deleted_on_uninstall(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".cursor").mkdir()
        install(tmp_path, carrier)
        write(tmp_path, RULE, read(tmp_path, RULE).replace("\n", "\r\n"))

        assert plan_init(read_project_state(tmp_path), carrier, InitOptions()).is_empty
        uninstall(tmp_path)
        assert not (tmp_path / RULE).exists()

    def test_uninstall_keeps_the_users_lines_below_a_created_replit_md_section(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".replit").write_text("")
        install(tmp_path, carrier)
        write(tmp_path, "replit.md", read(tmp_path, "replit.md") + "\nMine.\n")

        uninstall(tmp_path)

        assert read(tmp_path, "replit.md") == "\nMine.\n"


class TestRefusals:
    def test_a_cursor_directory_that_is_a_link_is_refused_and_nothing_is_written_behind_it(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        os.symlink(elsewhere, project / ".cursor")

        report = install(project, carrier)

        assert report.exit_code == 1
        assert list(elsewhere.iterdir()) == []

    def test_a_replit_md_that_is_a_link_out_of_the_project_is_not_written_through(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside.md"
        outside.write_text("secret\n")
        project = tmp_path / "project"
        project.mkdir()
        os.symlink(outside, project / "replit.md")

        report = install(project, carrier, InitOptions(write_existing=True))

        assert report.exit_code == 1
        assert outside.read_text() == "secret\n"

    def test_a_foreign_rule_file_at_our_path_is_refused_and_left_alone(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        write(tmp_path, RULE, "---\nalwaysApply: true\n---\nmine\n")

        report = install(tmp_path, carrier, InitOptions(force=True, write_existing=True))

        assert report.exit_code == 1
        assert read(tmp_path, RULE) == "---\nalwaysApply: true\n---\nmine\n"

    def test_two_sections_in_a_rule_are_refused_and_the_file_is_left_alone(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".cursor").mkdir()
        install(tmp_path, carrier)
        doubled = read(tmp_path, RULE) + read(tmp_path, RULE).split("---\n", 2)[2]
        write(tmp_path, RULE, doubled)

        assert install(tmp_path, carrier).exit_code == 1
        assert read(tmp_path, RULE) == doubled
        assert uninstall(tmp_path).exit_code == 1
        assert read(tmp_path, RULE) == doubled

    def test_a_replit_md_whose_section_never_closes_is_refused_even_with_write_existing(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        broken = "# Notes\n<!-- narrativetrace:start x==1 -->\nno end\n"
        write(tmp_path, "replit.md", broken)

        report = install(tmp_path, carrier, InitOptions(write_existing=True))

        assert report.exit_code == 1
        assert read(tmp_path, "replit.md") == broken

    def test_an_unreadable_replit_md_stops_the_run_before_anything_is_written(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / "replit.md").write_bytes(b"\xff\xfe\x00")

        with pytest.raises(ValueError, match=r"replit\.md"):
            read_project_state(tmp_path)

    def test_a_replit_md_that_is_a_directory_is_reported_and_left_intact(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / "replit.md").mkdir()
        write(tmp_path, "replit.md/keep.txt", "kept")

        report = install(tmp_path, carrier)

        assert report.exit_code == 1
        assert read(tmp_path, "replit.md/keep.txt") == "kept"

    def test_a_cursor_that_is_a_file_is_reported_and_left_intact(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        write(tmp_path, ".cursor", "not a directory")

        report = install(tmp_path, carrier)

        assert report.exit_code == 1
        assert read(tmp_path, ".cursor") == "not a directory"


class TestTheDoctorSeesWhatInstallWrote:
    def test_every_detected_pointer_reads_back_as_a_section_carrying_the_carriers_stamp(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".replit").write_text("")
        install(tmp_path, carrier)

        readings = read_pointer_readings(read_project_state(tmp_path))

        assert [(r.platform_id, r.status.value, r.coordinate) for r in readings] == [
            ("cursor", "section", carrier.coordinate),
            ("replit", "section", carrier.coordinate),
        ]
        assert all(isinstance(r, PointerReading) for r in readings)
