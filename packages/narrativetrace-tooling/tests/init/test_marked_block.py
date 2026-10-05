# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The managed block is found by its markers, and everything the installer does to a consumer file
is expressed as an edit of that region. These cases pin the marker rule itself — column 0, outside
fenced code — and the reversibility every ``init``/``uninstall`` round trip depends on.

Named after the Java port's ``MarkedBlockTest`` so the two lists diff.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.marked_block import END, START, Region

BLOCK = (
    "<!-- narrativetrace:start narrativetrace-skills==1.2.3 -->\n"
    "## NarrativeTrace\n"
    "<!-- narrativetrace:end -->\n"
)

BOM = "﻿"

NOT_TEXT: Any = None
"""What a guard exists for: the "no such file" of a reader that hands back text or nothing."""

_REGION = Region(0, 0, 1, "")


class TestFindingTheRegion:
    def test_finds_one_region_and_reads_its_coordinate(self) -> None:
        text = "# Title\n\n" + BLOCK

        scan = marked_block.scan(text)

        assert scan.problems == ()
        assert len(scan.regions) == 1
        assert scan.regions[0].coordinate == "narrativetrace-skills==1.2.3"
        assert text[scan.regions[0].start : scan.regions[0].end] == BLOCK

    def test_finds_a_region_whose_opening_marker_carries_no_coordinate(self) -> None:
        scan = marked_block.scan(f"{START} -->\nbody\n{END}\n")

        assert len(scan.regions) == 1
        assert scan.regions[0].coordinate == ""

    def test_reads_no_coordinate_from_an_opening_marker_that_never_closes(self) -> None:
        """The marker's own HTML comment never closes, so there is no coordinate to read — but the
        region is still a region, because the ``narrativetrace:end`` line below it pairs up."""
        scan = marked_block.scan(f"{START} oops\nbody\n{END}\n")

        assert len(scan.regions) == 1
        assert scan.regions[0].coordinate == ""

    def test_finds_two_regions_so_the_caller_can_refuse_them(self) -> None:
        scan = marked_block.scan(BLOCK + "\ntext\n\n" + BLOCK)

        assert len(scan.regions) == 2
        assert scan.problems == ()

    def test_reports_a_start_with_no_end_naming_the_line(self) -> None:
        scan = marked_block.scan(f"a\n{START} -->\nb\n")

        assert scan.regions == ()
        assert len(scan.problems) == 1
        assert "line 2" in scan.problems[0]
        assert "no end" in scan.problems[0]

    def test_reports_an_end_with_no_start_naming_the_line(self) -> None:
        scan = marked_block.scan(f"a\n{END}\n")

        assert len(scan.problems) == 1
        assert "line 2" in scan.problems[0]
        assert "no start" in scan.problems[0]

    def test_reports_a_second_start_before_the_first_end(self) -> None:
        scan = marked_block.scan(f"{START} -->\n{START} -->\n{END}\n")

        assert len(scan.problems) == 1
        assert "line 2" in scan.problems[0]

    def test_one_well_formed_region_and_nothing_questionable_is_what_callers_ask_for(self) -> None:
        assert marked_block.scan(BLOCK).has_exactly_one_region() is True
        assert marked_block.scan(BLOCK + BLOCK).has_exactly_one_region() is False
        assert marked_block.scan("").has_exactly_one_region() is False
        assert marked_block.scan(f"{END}\n" + BLOCK).has_exactly_one_region() is False


class TestWhatIsNotAMarker:
    """The near misses. The marker rule is narrow on purpose, so a document that SHOWS the markers
    keeps its own meaning and this repository's own ``narrativetrace:skills:*`` markers are not
    consumer markers."""

    def test_ignores_a_marker_inside_a_fenced_code_block(self) -> None:
        scan = marked_block.scan("# Docs\n\n```\n" + BLOCK + "```\n")

        assert scan.regions == ()
        assert scan.problems == ()

    def test_ignores_a_marker_inside_a_tilde_fenced_code_block(self) -> None:
        assert marked_block.scan("~~~\n" + BLOCK + "~~~\n").regions == ()

    def test_sees_a_marker_again_after_the_fence_closes(self) -> None:
        text = f"```\n{START} -->\n```\n" + BLOCK

        assert len(marked_block.scan(text).regions) == 1

    def test_ignores_an_indented_marker(self) -> None:
        text = f"  {START} -->\n  {END}\n"

        assert marked_block.scan(text).regions == ()
        assert marked_block.scan(text).problems == ()

    def test_ignores_this_repositorys_own_skills_markers(self) -> None:
        text = "<!-- narrativetrace:skills:start -->\nx\n<!-- narrativetrace:skills:end -->\n"

        assert marked_block.scan(text).regions == ()
        assert marked_block.scan(text).problems == ()

    def test_finds_a_marker_on_the_first_line_behind_a_byte_order_mark(self) -> None:
        scan = marked_block.scan(BOM + BLOCK)

        assert len(scan.regions) == 1

    def test_ignores_a_byte_order_mark_that_is_not_on_the_first_line(self) -> None:
        """A BOM only means "this file starts here" on line 1. Anywhere else it is a character in
        the line, so a marker behind one is not at column 0."""
        scan = marked_block.scan("# Title\n" + BOM + BLOCK)

        assert scan.regions == ()
        assert len(scan.problems) == 1

    def test_finds_a_region_whose_end_marker_is_the_last_line_without_a_trailing_newline(
        self,
    ) -> None:
        text = f"{START} -->\nbody\n{END}"

        scan = marked_block.scan(text)

        assert len(scan.regions) == 1
        assert text[scan.regions[0].start : scan.regions[0].end] == text


class TestEditing:
    def test_replaces_only_the_region_and_leaves_the_rest_byte_for_byte(self) -> None:
        text = "# Title\n\n" + BLOCK + "\ntail\n"
        region = marked_block.scan(text).regions[0]

        assert marked_block.replace(text, region, "<!-- new -->\n") == (
            "# Title\n\n<!-- new -->\n\ntail\n"
        )

    def test_replace_preserves_windows_line_endings(self) -> None:
        text = "# Title\r\n\r\n" + BLOCK.replace("\n", "\r\n")
        region = marked_block.scan(text).regions[0]

        replaced = marked_block.replace(text, region, marked_block.with_eol("x\n", "\r\n"))

        assert replaced == "# Title\r\n\r\nx\r\n"

    def test_appends_after_exactly_one_blank_line(self) -> None:
        assert marked_block.append("# Title\n", BLOCK) == "# Title\n\n" + BLOCK

    def test_appends_to_a_file_without_a_trailing_newline_by_adding_one(self) -> None:
        assert marked_block.append("# Title", BLOCK) == "# Title\n\n" + BLOCK

    def test_appends_to_an_empty_file_without_a_leading_blank_line(self) -> None:
        assert marked_block.append("", BLOCK) == BLOCK

    def test_appends_with_the_files_own_line_ending(self) -> None:
        crlf = BLOCK.replace("\n", "\r\n")

        assert marked_block.append("# Title\r\n", crlf) == "# Title\r\n\r\n" + crlf

    @pytest.mark.parametrize("original", ["# Title\n", "a\n\n\n", "x\r\n", "# T\r\n\r\n", ""])
    def test_removing_what_was_appended_restores_the_file_byte_for_byte(
        self, original: str
    ) -> None:
        block = marked_block.with_eol(BLOCK, marked_block.eol_of(original))
        appended = marked_block.append(original, block)

        region = marked_block.scan(appended).regions[0]

        assert marked_block.remove(appended, region) == original

    def test_removing_a_block_at_the_start_of_the_file_leaves_the_rest(self) -> None:
        text = BLOCK + "tail\n"
        region = marked_block.scan(text).regions[0]

        assert marked_block.remove(text, region) == "tail\n"

    def test_removing_a_line_takes_the_blank_line_an_append_would_have_added(self) -> None:
        text = marked_block.append("# Project\n", "@AGENTS.md\n")
        line = marked_block.line_is(text, "@AGENTS.md")

        assert line is not None
        assert marked_block.remove(text, line) == "# Project\n"


class TestFindingALine:
    def test_finds_the_exact_line_outside_a_fence(self) -> None:
        assert marked_block.line_is("a\n@AGENTS.md\nb\n", "@AGENTS.md") is not None
        assert marked_block.line_is("```\n@AGENTS.md\n```\n", "@AGENTS.md") is None
        assert marked_block.line_is("see `@AGENTS.md`\n", "@AGENTS.md") is None
        assert marked_block.line_is("@AGENTS.md  \n", "@AGENTS.md") is None

    def test_ignoring_trailing_space_still_counts_a_line_a_reader_would_read_as_there(self) -> None:
        found = marked_block.line_is_ignoring_trailing_space("@AGENTS.md   \n", "@AGENTS.md")

        assert found is not None
        assert found.number == 1
        assert marked_block.line_is_ignoring_trailing_space("  @AGENTS.md\n", "@AGENTS.md") is None

    def test_finds_the_first_of_two_identical_lines(self) -> None:
        found = marked_block.line_is("@AGENTS.md\n@AGENTS.md\n", "@AGENTS.md")

        assert found is not None
        assert found.number == 1


class TestUnfinishedFences:
    @pytest.mark.parametrize(
        ("text", "inside"),
        [
            ("# Title\n\n```\ncode\n", True),
            ("~~~\ncode\n", True),
            ("```\ncode\n```\n", False),
            ("```\na\n```\ntext\n```\nb\n", True),
            ("# Title\n", False),
            ("", False),
            ("  ```\nindented, not a fence\n", False),
        ],
    )
    def test_knows_when_a_file_ends_inside_a_fence_that_was_never_closed(
        self, text: str, inside: bool
    ) -> None:
        assert marked_block.ends_inside_fence(text) is inside


class TestLineEndings:
    def test_reads_the_files_line_ending_from_its_first_terminator(self) -> None:
        assert marked_block.eol_of("a\r\nb\n") == "\r\n"
        assert marked_block.eol_of("a\nb\r\n") == "\n"
        assert marked_block.eol_of("no terminator") == "\n"
        assert marked_block.eol_of("") == "\n"

    def test_reads_the_line_ending_of_a_file_that_starts_with_a_blank_line(self) -> None:
        assert marked_block.eol_of("\nx") == "\n"
        assert marked_block.eol_of("\r\nx") == "\r\n"

    def test_treats_a_lone_carriage_return_as_a_finished_line(self) -> None:
        assert marked_block.append("x\r", BLOCK) == "x\r\n" + BLOCK

    def test_rewrites_a_blocks_line_endings(self) -> None:
        assert marked_block.with_eol("a\nb\n", "\r\n") == "a\r\nb\r\n"
        assert marked_block.with_eol("a\r\nb\r\n", "\n") == "a\nb\n"
        assert marked_block.with_eol("a\r\nb\r\n", "\r\n") == "a\r\nb\r\n"

    def test_splits_lines_keeping_their_terminators_so_offsets_stay_exact(self) -> None:
        assert marked_block.split_keeping_terminators("a\r\nb\nc") == ("a\r\n", "b\n", "c")
        assert marked_block.split_keeping_terminators("") == ()


class TestGuards:
    """Every entry point guards its text. ``None`` is the value that matters: these functions are
    reached from a reader that returns "the file, or nothing", and a ``None`` slipping through would
    otherwise surface as a ``TypeError`` from a slice deep inside a scan."""

    @pytest.mark.parametrize(
        "call",
        [
            lambda: marked_block.scan(NOT_TEXT),
            lambda: marked_block.lines(NOT_TEXT),
            lambda: marked_block.append(NOT_TEXT, "x"),
            lambda: marked_block.append("x", NOT_TEXT),
            lambda: marked_block.eol_of(NOT_TEXT),
            lambda: marked_block.with_eol(NOT_TEXT, "\n"),
            lambda: marked_block.with_eol("x\n", NOT_TEXT),
            lambda: marked_block.ends_inside_fence(NOT_TEXT),
            lambda: marked_block.split_keeping_terminators(NOT_TEXT),
            lambda: marked_block.replace("x\n", _REGION, NOT_TEXT),
            lambda: marked_block.remove(NOT_TEXT, _REGION),
        ],
    )
    def test_refuses_text_that_is_not_text(self, call: Callable[[], object]) -> None:
        with pytest.raises(TypeError, match=r"a marked block reads text, never NoneType"):
            call()
