# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The provenance line decides, years later, whether a skill directory is ours. These cases pin
where it goes (after the frontmatter, never before), what counts as one (column 0, whole line), and
that stamping is idempotent.

Named after the Java port's ``ProvenanceTest`` so the two lists diff.
"""

from __future__ import annotations

from typing import Any

import pytest

from narrativetrace_tooling.init import provenance
from narrativetrace_tooling.init.provenance import PREFIX, SUFFIX

COORDINATE = "narrativetrace-skills==1.2.3"

PAGE = "---\nname: narrativetrace-doctor\ndescription: d\n---\n\nBody\n"

NOT_TEXT: Any = None


class TestTheLineItWrites:
    def test_reads_back_the_coordinate_it_wrote(self) -> None:
        stamped = provenance.stamp(PAGE, COORDINATE)

        assert provenance.coordinate_in(stamped) == COORDINATE

    def test_reads_a_pep_440_pin_which_is_this_runtimes_coordinate_form(self) -> None:
        """The coordinate is one token in every runtime and this one's is a pin, so the ``==`` has
        to survive a round trip through the line that carries it."""
        assert provenance.line(COORDINATE) == (
            "<!-- installed by narrativetrace init from narrativetrace-skills==1.2.3"
            " — edit the catalogue, not this file -->"
        )

    def test_puts_the_line_directly_after_the_frontmatter_never_before_it(self) -> None:
        stamped = provenance.stamp(PAGE, COORDINATE)

        assert stamped == (
            "---\nname: narrativetrace-doctor\ndescription: d\n---\n"
            + provenance.line(COORDINATE)
            + "\n\nBody\n"
        )
        assert stamped.startswith("---\n")

    def test_puts_the_line_at_the_top_of_a_page_without_frontmatter(self) -> None:
        stamped = provenance.stamp("Body only\n", COORDINATE)

        assert stamped == provenance.line(COORDINATE) + "\n\nBody only\n"
        assert provenance.coordinate_in(stamped) == COORDINATE

    def test_treats_an_unclosed_frontmatter_fence_as_no_frontmatter(self) -> None:
        stamped = provenance.stamp("---\nname: x\nbody\n", COORDINATE)

        assert stamped.startswith(provenance.line(COORDINATE))

    def test_stamping_twice_is_stamping_once(self) -> None:
        once = provenance.stamp(PAGE, COORDINATE)

        assert provenance.stamp(once, COORDINATE) == once

    def test_restamping_replaces_an_older_coordinate(self) -> None:
        older = provenance.stamp(PAGE, "narrativetrace-skills==0.0.9")

        newer = provenance.stamp(older, COORDINATE)

        assert provenance.coordinate_in(newer) == COORDINATE
        assert "0.0.9" not in newer
        assert newer == provenance.stamp(PAGE, COORDINATE)

    def test_keeps_the_files_line_endings(self) -> None:
        stamped = provenance.stamp(PAGE.replace("\n", "\r\n"), COORDINATE)

        assert "\r\r" not in stamped
        assert "---\r\n" + provenance.line(COORDINATE) + "\r\n" in stamped
        assert provenance.coordinate_in(stamped) == COORDINATE

    def test_stamps_an_empty_page(self) -> None:
        assert provenance.stamp("", COORDINATE) == provenance.line(COORDINATE) + "\n\n"


class TestWhatIsNotAProvenanceLine:
    def test_ignores_a_line_that_only_looks_like_provenance(self) -> None:
        indented = "---\nx\n---\n  " + provenance.line(COORDINATE) + "\n"
        truncated = "---\nx\n---\n" + PREFIX + COORDINATE + "\n"
        unclosed_comment = "---\nx\n---\n" + PREFIX + COORDINATE + SUFFIX[: -len(" -->")] + "\n"

        assert provenance.coordinate_in(indented) is None
        assert provenance.coordinate_in(truncated) is None
        assert provenance.coordinate_in(unclosed_comment) is None
        assert provenance.coordinate_in("") is None

    def test_reads_no_coordinate_from_a_line_that_names_none(self) -> None:
        """Prefix and suffix meet with nothing between them. The length guard is what catches it:
        the prefix ends with a space and the suffix starts with one, so the two OVERLAP in a
        hand-edited line and a naive startswith/endswith pair would read a coordinate of ``""``."""
        empty = PREFIX + SUFFIX

        assert provenance.coordinate_in("---\nx\n---\n" + empty + "\n") is None
        assert provenance.stamp("---\nx\n---\n" + empty + "\n", COORDINATE) == (
            "---\nx\n---\n" + provenance.line(COORDINATE) + "\n"
        )

    def test_reads_a_line_shorter_than_the_prefix_and_suffix_together(self) -> None:
        """The overlap the guard above exists for, at its shortest: the two halves share their one
        space, so the line is one character shorter than their lengths added up."""
        overlapping = PREFIX.rstrip() + SUFFIX

        assert len(overlapping) == len(PREFIX) + len(SUFFIX) - 1
        assert provenance.coordinate_in("---\nx\n---\n" + overlapping + "\n") is None

    def test_finds_the_line_in_a_page_whose_last_line_has_no_terminator(self) -> None:
        page = "---\nx\n---\n" + provenance.line(COORDINATE)

        assert provenance.coordinate_in(page) == COORDINATE

    def test_reads_the_first_coordinate_when_a_page_somehow_carries_two(self) -> None:
        page = (
            "---\nx\n---\n"
            + provenance.line(COORDINATE)
            + "\n"
            + provenance.line("narrativetrace-skills==9.9.9")
            + "\n"
        )

        assert provenance.coordinate_in(page) == COORDINATE

    def test_stamping_a_page_with_two_leaves_exactly_one(self) -> None:
        page = (
            "---\nx\n---\n"
            + provenance.line("narrativetrace-skills==0.0.1")
            + "\n"
            + provenance.line("narrativetrace-skills==0.0.2")
            + "\n"
        )

        stamped = provenance.stamp(page, COORDINATE)

        assert stamped.count(PREFIX) == 1
        assert provenance.coordinate_in(stamped) == COORDINATE


class TestGuards:
    def test_refuses_a_page_that_is_not_text(self) -> None:
        with pytest.raises(TypeError, match=r"text"):
            provenance.stamp(NOT_TEXT, COORDINATE)
        with pytest.raises(TypeError, match=r"text"):
            provenance.coordinate_in(NOT_TEXT)

    @pytest.mark.parametrize("coordinate", ["", "   "])
    def test_refuses_to_stamp_with_a_blank_coordinate(self, coordinate: str) -> None:
        with pytest.raises(ValueError, match=r"a provenance line names the carrier it came from"):
            provenance.line(coordinate)
        with pytest.raises(ValueError, match=r"a provenance line names the carrier it came from"):
            provenance.stamp(PAGE, coordinate)
