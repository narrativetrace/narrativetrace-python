# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial marker cases for the managed block: fences of different lengths and kinds and a
byte-order mark combined with CRLF line endings (the near-miss opening marker is pinned, fixed, in
``test_marked_block.py``).

Named by area so it cannot collide with ``test_marked_block.py`` at collection time.
"""

from __future__ import annotations

import pytest

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.marked_block import END, START

BOM = "﻿"
BLOCK = f"{START} narrativetrace-skills==1.2.3 -->\n## NarrativeTrace\n{END}\n"


def _crlf(text: str) -> str:
    return text.replace("\n", "\r\n")


class TestFenceClosers:
    @pytest.mark.xfail(
        strict=True,
        reason="the fence toggle ignores fence length: a ``` line closes a ```` fence, so the "
        "markers in the example are read as a live managed region",
    )
    def test_a_four_backtick_fence_holding_a_three_backtick_line_still_hides_its_markers(
        self,
    ) -> None:
        """CommonMark: a fence closes only on a run of at least the same length, so a ``` line
        inside a ```` example does not end it, and the markers after it are still example text."""
        text = f"````md\n```\n{BLOCK}````\n"

        scan = marked_block.scan(text)

        assert scan.regions == ()
        assert scan.problems == ()

    @pytest.mark.xfail(
        strict=True,
        reason="the fence toggle ignores fence character: a ``` line closes a ~~~ fence, so the "
        "markers in the example are read as a live managed region",
    )
    def test_a_tilde_fence_holding_a_backtick_line_still_hides_its_markers(self) -> None:
        """A ``~~~`` fence is closed only by ``~~~``; a backtick line inside it is code, not a
        closer, so the marker that follows is still inside the example."""
        text = f"~~~\n```\n{BLOCK}~~~\n"

        scan = marked_block.scan(text)

        assert scan.regions == ()
        assert scan.problems == ()


class TestByteOrderMarkWithCrlf:
    def test_replacing_a_region_on_line_one_of_a_crlf_file_keeps_mark_and_line_endings(
        self,
    ) -> None:
        text = BOM + _crlf(BLOCK + "tail\n")
        region = marked_block.scan(text).regions[0]

        replaced = marked_block.replace(text, region, marked_block.with_eol("NEW\n", "\r\n"))

        assert replaced == BOM + "NEW\r\ntail\r\n"

    def test_finds_a_line_on_line_one_behind_a_mark_with_crlf_and_reports_its_offset(self) -> None:
        text = BOM + "@AGENTS.md\r\nrest\r\n"

        found = marked_block.line_is(text, "@AGENTS.md")

        assert found is not None
        assert (found.start, found.end) == (1, len(BOM) + len("@AGENTS.md\r\n"))

    def test_a_crlf_start_marker_still_yields_its_coordinate_without_the_carriage_return(
        self,
    ) -> None:
        text = _crlf(f"{START} a-b==1.2.3 -->\nx\n{END}\n")

        region = marked_block.scan(text).regions[0]

        assert region.coordinate == "a-b==1.2.3"


class TestBareEndMarker:
    def test_an_end_marker_with_trailing_spaces_still_closes_its_region(self) -> None:
        text = f"{START} -->\nbody\n{END}   \n"

        scan = marked_block.scan(text)

        assert len(scan.regions) == 1
        assert scan.problems == ()


class TestMarkOnlyFile:
    @pytest.mark.xfail(
        strict=True,
        reason="append treats a BOM-only file as non-empty: it returns BOM + two newlines + block "
        "instead of BOM + block (cosmetic; reachable via init --write-existing)",
    )
    def test_appending_to_a_file_that_is_only_a_byte_order_mark_adds_just_the_block(self) -> None:
        """Every module's own rule says a mark alone is not content: ``without_byte_order_mark``
        exists so "is anything left?" answers no. ``append`` must agree, and an empty-looking file
        must not gain a leading blank line."""
        appended = marked_block.append(BOM, BLOCK)

        assert appended == BOM + BLOCK
