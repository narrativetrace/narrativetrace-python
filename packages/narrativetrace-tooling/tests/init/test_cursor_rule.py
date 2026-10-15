# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one Cursor rule file — ``.cursor/rules/narrativetrace.mdc`` — that points Cursor's agent at
the installed skills (Phase 8, platform pointers). A pure rendering."""

from __future__ import annotations

from typing import Any

import pytest

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.cursor_rule import FRONTMATTER, render_cursor_rule

TEXT = "Read the skills."


class TestRendering:
    def test_is_the_frontmatter_then_one_stamped_section(self) -> None:
        assert render_cursor_rule(TEXT, "narrativetrace-skills==1.2.3") == (
            "---\ndescription: Where the NarrativeTrace agent skills live in this project\n"
            "alwaysApply: true\n---\n"
            "<!-- narrativetrace:start narrativetrace-skills==1.2.3 -->\n"
            "Read the skills.\n"
            "<!-- narrativetrace:end -->\n"
        )

    def test_an_empty_coordinate_leaves_the_opening_marker_unstamped(self) -> None:
        rule = render_cursor_rule(TEXT, "")

        assert rule.splitlines()[4] == "<!-- narrativetrace:start -->"
        assert marked_block.scan(rule).regions[0].coordinate == ""

    def test_carries_exactly_one_region_and_the_frontmatter_first(self) -> None:
        rule = render_cursor_rule(TEXT, "x==1")

        assert rule.startswith(FRONTMATTER)
        assert marked_block.scan(rule).has_exactly_one_region()

    def test_the_frontmatter_always_applies_because_the_pointer_must_be_seen_every_turn(
        self,
    ) -> None:
        assert "alwaysApply: true\n" in FRONTMATTER

    @pytest.mark.parametrize(("text", "coordinate"), [("", "x"), (" \n", "x")])
    def test_refuses_a_blank_sentence(self, text: str, coordinate: str) -> None:
        with pytest.raises(ValueError, match="needs its text"):
            render_cursor_rule(text, coordinate)

    def test_refuses_a_missing_text_or_coordinate(self) -> None:
        missing: Any = None
        with pytest.raises(TypeError):
            render_cursor_rule(missing, "x")
        with pytest.raises(TypeError):
            render_cursor_rule(TEXT, missing)
