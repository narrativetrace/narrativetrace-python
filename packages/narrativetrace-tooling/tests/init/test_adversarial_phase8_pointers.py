# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial pointer cases through the installer's public surface: a reader reading an empty or
byte-order-marked pointer, the snapshot's own guards on platform ids and link facts, and an
uninstall of a CRLF, byte-order-marked pointer.

Named by area so it cannot collide with the other Phase 8 test modules at collection time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from narrativetrace_tooling.init import (
    InitOptions,
    ProjectState,
    plan_uninstall,
    read_pointer_readings,
    read_project_state,
)
from narrativetrace_tooling.init.action import DeleteFile, ReplaceBlock
from narrativetrace_tooling.init.cursor_rule import FRONTMATTER
from narrativetrace_tooling.init.marked_block import CREATED_NOTE, END, START
from narrativetrace_tooling.init.pointer_reading import Status

BOM = "﻿"
RULE = ".cursor/rules/narrativetrace.mdc"
REPLIT = "replit.md"
SECTION = f"{START} narrativetrace-skills==1.2.3 -->\n## NarrativeTrace\n{END}\n"


def _crlf(text: str) -> str:
    return text.replace("\n", "\r\n")


def _write(project: Path, relative: str, text: str) -> None:
    target = project / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))


@pytest.fixture
def cursor_project(tmp_path: Path) -> Path:
    (tmp_path / ".cursor").mkdir()
    return tmp_path


class TestReadingAnEmptyPointer:
    def test_an_empty_rule_file_is_foreign_not_absent(self, cursor_project: Path) -> None:
        """A zero-byte rule file is a file somebody made. Reporting it ABSENT would plan a create
        over it; it must read as foreign so the planner refuses it."""
        _write(cursor_project, RULE, "")

        readings = read_pointer_readings(read_project_state(cursor_project))

        assert [(r.platform_id, r.status) for r in readings] == [("cursor", Status.FOREIGN)]


class TestBytesOfAPointerAreKept:
    def test_a_replit_md_with_a_mark_and_crlf_is_read_byte_for_byte_and_its_section_found(
        self, tmp_path: Path
    ) -> None:
        text = BOM + _crlf(f"# App\n\n{SECTION}")
        _write(tmp_path, REPLIT, text)

        state = read_project_state(tmp_path)
        readings = read_pointer_readings(state)

        assert state.pointer_files[REPLIT] == text
        assert [(r.status, r.coordinate) for r in readings] == [
            (Status.SECTION, "narrativetrace-skills==1.2.3")
        ]


class TestSnapshotGuards:
    def test_a_detected_platform_id_must_match_the_table_exactly(self) -> None:
        """Ids are kebab-case cross-port contract strings; ``Cursor`` is not the row ``cursor``."""
        with pytest.raises(ValueError, match="platform table"):
            ProjectState(detected_platforms=frozenset({"Cursor"}))

    def test_a_pointer_cannot_be_both_read_and_behind_a_link(self) -> None:
        """Nothing is read through a link, so a path that is both is a state no reader produces."""
        with pytest.raises(ValueError, match="behind a link"):
            ProjectState(
                detected_platforms=frozenset({"cursor"}),
                pointer_files={RULE: SECTION},
                pointers_behind_links=frozenset({RULE}),
            )


class TestUninstallOfMarkedCrlfPointers:
    def test_a_created_crlf_replit_md_with_a_mark_is_deleted_outright(self) -> None:
        text = BOM + _crlf(f"{CREATED_NOTE}\n{SECTION}")
        state = ProjectState(pointer_files={REPLIT: text})

        actions = plan_uninstall(state, InitOptions()).actions

        assert [type(action) for action in actions] == [DeleteFile]

    def test_a_crlf_rule_keeps_the_users_crlf_line_below_ours_and_its_frontmatter(self) -> None:
        installed = _crlf(FRONTMATTER + SECTION)
        text = installed + "Team note\r\n"
        state = ProjectState(pointer_files={RULE: text})

        actions = plan_uninstall(state, InitOptions()).actions

        assert len(actions) == 1
        action = actions[0]
        assert isinstance(action, ReplaceBlock)
        assert action.after == _crlf(FRONTMATTER) + "Team note\r\n"
