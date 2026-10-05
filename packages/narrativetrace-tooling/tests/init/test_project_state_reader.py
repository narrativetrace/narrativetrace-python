# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Reads a real directory once, read-only: what the planners later decide from is decided here.

Named after the Java port's ``ProjectStateReaderTest`` so the two lists diff. Java's
Gradle-detection and ``gradle.properties`` cases become this runtime's own: a ``uv`` project, and
the output directory read out of ``narrativetrace.toml`` or ``[tool.narrativetrace]``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from narrativetrace_tooling.init import provenance
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.project_state import DEFAULT_OUTPUT_DIRECTORY, Presence
from narrativetrace_tooling.init.project_state_reader import read_project_state

MISSING: Any = None

BOM = "﻿"


def write(file: Path, content: str = "") -> None:
    """Writes BYTES, not text: ``write_text`` translates ``\\n`` to the platform terminator, which
    would make a CRLF fixture mean something different on Windows than it does here."""
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content.encode("utf-8"))


def installed_page(coordinate: str) -> str:
    return "---\nname: narrativetrace-doctor\n---\n" + provenance.line(coordinate) + "\n\nbody\n"


class TestReadingAProject:
    def test_reads_an_empty_directory_as_an_untouched_project(self, tmp_path: Path) -> None:
        state = read_project_state(tmp_path)

        assert state.agents_md is None
        assert state.claude_md is None
        assert state.claude_directory is False
        assert state.installed_skills == ()
        assert dict(state.marked_rule_files) == {}
        assert state.output_directory == DEFAULT_OUTPUT_DIRECTORY
        assert state.uv_project is False

    def test_reads_both_context_files_byte_for_byte(self, tmp_path: Path) -> None:
        write(tmp_path / "AGENTS.md", "# Agents\r\n\r\ntext")
        write(tmp_path / "CLAUDE.md", BOM + "# Claude\n")

        state = read_project_state(tmp_path)

        assert state.agents_md == "# Agents\r\n\r\ntext"
        assert state.claude_md == BOM + "# Claude\n"

    def test_sees_the_vendor_directory_even_when_it_holds_no_skills(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()

        assert read_project_state(tmp_path).claude_directory is True


class TestReadingWhatIsInstalled:
    def test_reads_an_installed_skill_with_its_provenance_coordinate(self, tmp_path: Path) -> None:
        page = installed_page("narrativetrace-skills==0.1.0")
        write(tmp_path / ".agents/skills/narrativetrace-doctor/SKILL.md", page)

        skill = read_project_state(tmp_path).installed_skill(
            SkillFlavour.AGENTS, "narrativetrace-doctor"
        )

        assert skill is not None
        assert skill.presence is Presence.OURS
        assert skill.coordinate == "narrativetrace-skills==0.1.0"
        assert skill.body == page
        assert skill.page == Path(".agents/skills/narrativetrace-doctor/SKILL.md")

    def test_reads_a_skill_directory_without_our_provenance_as_foreign(
        self, tmp_path: Path
    ) -> None:
        write(tmp_path / ".agents/skills/somebody-elses/SKILL.md", "---\nname: x\n---\nbody\n")
        (tmp_path / ".claude/skills/no-page-at-all").mkdir(parents=True)

        state = read_project_state(tmp_path)

        theirs = state.installed_skill(SkillFlavour.AGENTS, "somebody-elses")
        pageless = state.installed_skill(SkillFlavour.CLAUDE, "no-page-at-all")
        assert theirs is not None and theirs.presence is Presence.FOREIGN
        assert pageless is not None and pageless.presence is Presence.FOREIGN

    def test_reads_a_file_sitting_where_a_skill_directory_belongs_as_not_a_directory(
        self, tmp_path: Path
    ) -> None:
        write(tmp_path / ".agents/skills/narrativetrace-doctor", "not a directory\n")

        skill = read_project_state(tmp_path).installed_skill(
            SkillFlavour.AGENTS, "narrativetrace-doctor"
        )

        assert skill is not None
        assert skill.presence is Presence.NOT_A_DIRECTORY
        assert skill.body == ""

    def test_reads_both_flavours_independently(self, tmp_path: Path) -> None:
        write(
            tmp_path / ".agents/skills/narrativetrace-doctor/SKILL.md",
            installed_page("narrativetrace-skills==0.1.0"),
        )
        write(tmp_path / ".claude/skills/narrativetrace-doctor/SKILL.md", "---\nx\n---\nother\n")

        state = read_project_state(tmp_path)

        assert len(state.installed_skills) == 2
        agents = state.installed_skill(SkillFlavour.AGENTS, "narrativetrace-doctor")
        vendor = state.installed_skill(SkillFlavour.CLAUDE, "narrativetrace-doctor")
        assert agents is not None and agents.presence is Presence.OURS
        assert vendor is not None and vendor.presence is Presence.FOREIGN
        assert state.installed_skill(SkillFlavour.CLAUDE, "absent") is None

    def test_bounds_how_many_skill_directories_it_reads(self, tmp_path: Path) -> None:
        for index in range(5):
            (tmp_path / f".agents/skills/skill-{index}").mkdir(parents=True)

        state = read_project_state(tmp_path, max_skill_directories=3)

        assert [skill.name for skill in state.installed_skills] == [
            "skill-0",
            "skill-1",
            "skill-2",
        ]

    def test_reads_skill_directories_in_name_order_so_a_bounded_read_is_reproducible(
        self, tmp_path: Path
    ) -> None:
        for name in ("zeta", "alpha", "mid"):
            (tmp_path / ".agents/skills" / name).mkdir(parents=True)

        state = read_project_state(tmp_path)

        assert [skill.name for skill in state.installed_skills] == ["alpha", "mid", "zeta"]


class TestReadingAVendorRuleFile:
    def test_reads_a_rule_file_only_when_it_carries_our_markers(self, tmp_path: Path) -> None:
        marked = "# rules\n<!-- narrativetrace:start -->\nx\n<!-- narrativetrace:end -->\n"
        write(tmp_path / ".cursorrules", marked)
        write(tmp_path / ".github/copilot-instructions.md", "# no markers here\n")

        assert dict(read_project_state(tmp_path).marked_rule_files) == {".cursorrules": marked}

    def test_reads_a_rule_file_whose_markers_do_not_pair_up_so_the_planner_can_refuse_it(
        self, tmp_path: Path
    ) -> None:
        broken = "# rules\n<!-- narrativetrace:start -->\nno end below it\n"
        write(tmp_path / ".cursorrules", broken)

        assert dict(read_project_state(tmp_path).marked_rule_files) == {".cursorrules": broken}

    def test_reads_the_second_rule_file_too(self, tmp_path: Path) -> None:
        marked = "<!-- narrativetrace:start -->\nx\n<!-- narrativetrace:end -->\n"
        write(tmp_path / ".github/copilot-instructions.md", marked)

        assert ".github/copilot-instructions.md" in read_project_state(tmp_path).marked_rule_files


class TestReadingWhereTracesLand:
    def test_reads_the_output_directory_from_the_standalone_config(self, tmp_path: Path) -> None:
        write(tmp_path / "narrativetrace.toml", 'output_dir = "out/narrative"\n')

        assert read_project_state(tmp_path).output_directory == "out/narrative"

    def test_reads_the_output_directory_from_the_pyproject_table(self, tmp_path: Path) -> None:
        write(tmp_path / "pyproject.toml", '[tool.narrativetrace]\noutput_dir = "build/traces"\n')

        state = read_project_state(tmp_path)

        assert state.output_directory == "build/traces"
        assert state.uv_project is True

    def test_prefers_the_standalone_config_over_the_pyproject_table(self, tmp_path: Path) -> None:
        write(tmp_path / "narrativetrace.toml", 'output_dir = "standalone"\n')
        write(tmp_path / "pyproject.toml", '[tool.narrativetrace]\noutput_dir = "table"\n')

        assert read_project_state(tmp_path).output_directory == "standalone"

    def test_ignores_another_key_and_an_empty_value(self, tmp_path: Path) -> None:
        write(tmp_path / "narrativetrace.toml", 'level = "DETAIL"\noutput_directory = "x"\n')

        assert read_project_state(tmp_path).output_directory == DEFAULT_OUTPUT_DIRECTORY

        write(tmp_path / "narrativetrace.toml", 'output_dir = "   "\n')

        assert read_project_state(tmp_path).output_directory == DEFAULT_OUTPUT_DIRECTORY

    def test_ignores_an_output_directory_that_is_not_a_string(self, tmp_path: Path) -> None:
        write(tmp_path / "narrativetrace.toml", "output_dir = 7\n")

        assert read_project_state(tmp_path).output_directory == DEFAULT_OUTPUT_DIRECTORY

    def test_degrades_a_malformed_config_to_the_default_rather_than_failing_the_run(
        self, tmp_path: Path
    ) -> None:
        """The runtime's own reader degrades the same way. One directory name for one line of prose
        is not worth refusing an install over, and a project with a broken config file has a problem
        the installer is not the one to report."""
        write(tmp_path / "narrativetrace.toml", "output_dir = [unclosed\n")

        assert read_project_state(tmp_path).output_directory == DEFAULT_OUTPUT_DIRECTORY

    def test_reads_a_pyproject_with_no_narrativetrace_table_at_all(self, tmp_path: Path) -> None:
        write(tmp_path / "pyproject.toml", "[project]\nname = 'demo'\n")

        assert read_project_state(tmp_path).output_directory == DEFAULT_OUTPUT_DIRECTORY


class TestReadingHowCommandsAreSpelled:
    def test_a_lock_file_alone_makes_it_a_uv_project(self, tmp_path: Path) -> None:
        write(tmp_path / "uv.lock", "version = 1\n")

        assert read_project_state(tmp_path).uv_project is True

    def test_a_directory_with_neither_is_not_one(self, tmp_path: Path) -> None:
        write(tmp_path / "main.py", "print('hi')\n")

        assert read_project_state(tmp_path).uv_project is False


class TestWhenTheReaderRefuses:
    def test_refuses_to_read_a_project_that_is_not_a_directory(self, tmp_path: Path) -> None:
        file = tmp_path / "a-file"
        write(file, "x")

        with pytest.raises(ValueError, match=r"is not a directory"):
            read_project_state(file)

    def test_refuses_to_read_no_project_at_all(self) -> None:
        with pytest.raises(TypeError, match=r"a project directory must be given"):
            read_project_state(MISSING)

    def test_fails_loudly_when_a_file_it_must_plan_against_cannot_be_read(
        self, tmp_path: Path
    ) -> None:
        """ "Unreadable" and "absent" lead to OPPOSITE plans — absent means create, and creating
        over a file we could not read would destroy it."""
        (tmp_path / "AGENTS.md").write_bytes(b"\xff\xfe\xfd")

        with pytest.raises(ValueError, match=r"cannot read .*AGENTS\.md"):
            read_project_state(tmp_path)

    def test_fails_loudly_when_an_installed_page_cannot_be_read(self, tmp_path: Path) -> None:
        page = tmp_path / ".agents/skills/narrativetrace-doctor/SKILL.md"
        page.parent.mkdir(parents=True)
        page.write_bytes(b"\xff\xfe\xfd")

        with pytest.raises(ValueError, match=r"cannot read .*SKILL\.md"):
            read_project_state(tmp_path)

    def test_fails_loudly_when_an_install_root_cannot_be_listed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An install root that exists and cannot be listed is not an empty one: "empty" would make
        the planner create every page over whatever is really in there. The failure is injected
        because a permission this container cannot set is still one a consumer's filesystem can."""
        (tmp_path / ".agents/skills").mkdir(parents=True)
        listable = Path.iterdir

        def refuse(self: Path) -> Iterator[Path]:
            if self.name == "skills":
                raise OSError(13, "Permission denied")
            return listable(self)

        monkeypatch.setattr(Path, "iterdir", refuse)

        with pytest.raises(ValueError, match=r"cannot list .*skills"):
            read_project_state(tmp_path)
