# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The span id grammar and its derivation from tree position (:mod:`narrativetrace.render.span_id`).

Mirrors the reference ``SpanIdTest``: an id is ``#`` then dot-separated runs of ASCII digits,
derived from position, never stored.
"""

from __future__ import annotations

import re

import pytest

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.render import span_id
from narrativetrace.signature import MethodSignature


def _node(
    class_name: str, method_name: str, info: ConcurrencyInfo | None, *, launcher: bool = False
) -> TraceNode:
    return TraceNode(
        signature=MethodSignature(class_name, method_name, []),
        outcome=None if launcher else Returned(None),
        concurrency=info,
    )


class TestDerivation:
    def test_a_root_is_its_position_and_a_child_extends_its_parents_path(self) -> None:
        assert span_id.child(None, 3) == "#3"
        assert span_id.child("#1.3", 2) == "#1.3.2"

    def test_a_fork_group_is_numbered_by_signature_but_listed_in_capture_order(self) -> None:
        fork = ConcurrencyInfo("g", ConcurrencyKind.FORK_JOIN)
        faf = ConcurrencyInfo("f", ConcurrencyKind.FIRE_AND_FORGET)
        siblings = [
            _node("Zed", "a", None),
            _node("Delta", "z", fork),
            _node("Bravo", "z", fork),
            _node("Delta", "a", fork),
            _node("Launcher", "go", faf, launcher=True),
            _node("Alpha", "a", None),
        ]

        assert span_id.ids_of(siblings, "#4") == ["#4.1", "#4.4", "#4.2", "#4.3", "#4.5", "#4.6"]

    def test_equal_signatures_in_one_group_keep_capture_order(self) -> None:
        fork = ConcurrencyInfo("g", ConcurrencyKind.FORK_JOIN)
        first = _node("Same", "run", fork)
        second = _node("Same", "run", fork)

        assert span_id.ids_of([first, second], None) == ["#1", "#2"]

    def test_an_empty_sibling_list_has_no_ids(self) -> None:
        assert span_id.ids_of([], None) == []


class TestReadingALine:
    def test_without_id_removes_the_id_after_the_indent_and_keeps_the_indent(self) -> None:
        assert span_id.without_id("    #1.12.3 - A.b()") == "    - A.b()"
        assert span_id.without_id("#7 ~ fire-and-forget") == "~ fire-and-forget"

    @pytest.mark.parametrize(
        "line",
        [
            "- A.b()",
            "  ~ fork [2]",
            "#",
            "# - A.b()",
            "#1. - A.b()",
            "#.1 - A.b()",
            "#1..2 - A.b()",
            "#1a - A.b()",
            "#1",
            "#1\t- A.b()",
            "\t#1 - A.b()",
            "",
            "scenario: #1 rocks",
            "#\u0661 - A.b()",
            "#1\u00a0- A.b()",
        ],
    )
    def test_a_line_without_a_well_formed_id_is_left_as_written_and_cites_nothing(
        self, line: str
    ) -> None:
        assert span_id.without_id(line) == line
        assert span_id.of(line) is None

    def test_of_reads_the_id_a_line_opens_with(self) -> None:
        assert span_id.of("  #1.2 - A.b()") == "#1.2"


class TestWellFormed:
    @pytest.mark.parametrize("text", ["#1", "#1.20.3", "#0"])
    def test_exactly_one_id_is_well_formed(self, text: str) -> None:
        assert span_id.is_well_formed(text)

    @pytest.mark.parametrize(
        "text", ["#1.2 ", " #1.2", "#1.2#3", "", "#", "#1.", "#.1", "#\u0661", "#1\n", None]
    )
    def test_anything_else_is_not(self, text: str | None) -> None:
        assert not span_id.is_well_formed(text)


class TestRange:
    def test_a_range_cites_first_and_last(self) -> None:
        assert span_id.cite_range(["#1.2", "#1.3", "#1.4"]) == "#1.2\u2013#1.4"

    def test_a_one_span_range_is_the_id_itself(self) -> None:
        assert span_id.cite_range(["#1.2"]) == "#1.2"

    def test_an_empty_range_cites_nothing_and_is_refused(self) -> None:
        with pytest.raises(ValueError, match=re.escape("a range cites at least one span")):
            span_id.cite_range([])
