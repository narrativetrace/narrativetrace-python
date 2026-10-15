# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What one detected platform's pointer file looks like in a project — the installer's own reading,
handed to the doctor so both agree on what "present" means.

Named after the Java port's ``PointerReadingTest`` so the two lists diff.
"""

from __future__ import annotations

from typing import Any

import pytest

from narrativetrace_tooling.init.cursor_rule import render_cursor_rule
from narrativetrace_tooling.init.pointer_reading import PointerReading, Status, read_all
from narrativetrace_tooling.init.project_state import ProjectState

RULE = ".cursor/rules/narrativetrace.mdc"
SECTION = (
    "<!-- narrativetrace:start narrativetrace-skills==1.2.3 -->\nx\n<!-- narrativetrace:end -->\n"
)


class TestReadAll:
    def test_reads_nothing_for_a_project_on_no_platform(self) -> None:
        assert read_all(ProjectState()) == ()

    def test_reads_nothing_for_a_platform_with_no_pointer(self) -> None:
        state = ProjectState(detected_platforms={"antigravity", "github-copilot", "claude-code"})

        assert read_all(state) == ()

    def test_an_absent_pointer_of_a_detected_platform_is_reported_absent(self) -> None:
        reading = read_all(ProjectState(detected_platforms={"cursor"}))

        assert reading == (PointerReading("cursor", "Cursor", RULE, Status.ABSENT, ""),)

    def test_a_pointer_whose_platform_is_not_detected_is_not_read(self) -> None:
        state = ProjectState(pointer_files={RULE: render_cursor_rule("t", "x==1")})

        assert read_all(state) == ()

    def test_a_pointer_behind_a_link_is_linked_and_never_read(self) -> None:
        state = ProjectState(detected_platforms={"replit"}, pointers_behind_links={"replit.md"})

        assert read_all(state)[0].status is Status.LINKED

    def test_a_file_without_exactly_one_section_is_foreign(self) -> None:
        for text in ("# Notes\n", SECTION + SECTION, "<!-- narrativetrace:start x -->\nno end\n"):
            state = ProjectState(detected_platforms={"replit"}, pointer_files={"replit.md": text})

            assert read_all(state)[0].status is Status.FOREIGN, text

    def test_a_file_with_one_section_is_a_section_carrying_its_coordinate(self) -> None:
        state = ProjectState(detected_platforms={"replit"}, pointer_files={"replit.md": SECTION})

        assert read_all(state) == (
            PointerReading(
                "replit", "Replit", "replit.md", Status.SECTION, "narrativetrace-skills==1.2.3"
            ),
        )

    def test_an_unstamped_section_carries_an_empty_coordinate(self) -> None:
        text = render_cursor_rule("t", "")
        state = ProjectState(detected_platforms={"cursor"}, pointer_files={RULE: text})

        assert read_all(state)[0] == PointerReading("cursor", "Cursor", RULE, Status.SECTION, "")

    def test_reads_in_platform_table_order_when_two_platforms_are_detected(self) -> None:
        state = ProjectState(detected_platforms={"replit", "cursor"})

        assert [r.platform_id for r in read_all(state)] == ["cursor", "replit"]

    def test_refuses_a_missing_state(self) -> None:
        missing: Any = None
        with pytest.raises(TypeError):
            read_all(missing)


class TestTheReadingIsChecked:
    def test_a_coordinate_belongs_to_a_section_only(self) -> None:
        with pytest.raises(ValueError, match="coordinate"):
            PointerReading("cursor", "Cursor", RULE, Status.ABSENT, "x==1")
