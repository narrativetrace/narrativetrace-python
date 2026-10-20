# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from pathlib import Path

import case_prompt
import pytest

_EVALS = Path(__file__).resolve().parent
_FORBIDDEN = ("Expected trajectory", "Grading", "graders/")


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "prompt.md"
    path.write_text(text, encoding="utf-8")
    return path


class TestABarePrompt:
    def test_is_sent_byte_for_byte(self, tmp_path: Path) -> None:
        text = "Set up NarrativeTrace.\n\n> not a quote to extract\n**Grading**\n  trailing  \n"
        assert case_prompt.prompt_for_agent(_write(tmp_path, text)) == text

    def test_a_first_line_that_only_resembles_the_case_marker_is_still_bare(
        self, tmp_path: Path
    ) -> None:
        for first in ("# Cases: x", "#Case: x", " # Case: x", "## Case: x"):
            text = f"{first}\n\n**Task prompt**\n\n> quoted\n"
            assert case_prompt.prompt_for_agent(_write(tmp_path, text)) == text


class TestACaseDocument:
    def test_is_sent_only_the_blockquote_under_the_task_prompt_line(self, tmp_path: Path) -> None:
        text = (
            "# Case: x\n\n**Fixture:** y\n\n**Task prompt** (given to the agent):\n\n"
            "> Do the thing.\n\n**Expected trajectory:** secret\n"
        )
        assert case_prompt.prompt_for_agent(_write(tmp_path, text)) == "Do the thing."

    def test_joins_wrapped_lines_with_one_space_and_keeps_paragraph_breaks(
        self, tmp_path: Path
    ) -> None:
        text = (
            "# Case: x\n\n**Task prompt:**\n\n\n> first line\n> wrapped on\n>\n> second paragraph\n"
            ">\n> third\n\nafter\n"
        )
        expected = "first line wrapped on\n\nsecond paragraph\n\nthird"
        assert case_prompt.prompt_for_agent(_write(tmp_path, text)) == expected

    def test_a_quote_marker_without_a_space_is_still_stripped(self, tmp_path: Path) -> None:
        text = "# Case: x\n**Task prompt:**\n>no space\n> and one\n"
        assert case_prompt.prompt_for_agent(_write(tmp_path, text)) == "no space and one"

    def test_a_blockquote_before_the_task_prompt_line_is_not_the_prompt(
        self, tmp_path: Path
    ) -> None:
        text = "# Case: x\n\n> a decoy\n\n**Task prompt:**\n\n> the real one\n"
        assert case_prompt.prompt_for_agent(_write(tmp_path, text)) == "the real one"

    def test_without_a_task_prompt_line_raises_naming_the_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "# Case: x\n\n> orphan quote\n")
        with pytest.raises(ValueError, match=str(path)):
            case_prompt.prompt_for_agent(path)

    def test_without_a_blockquote_raises_naming_the_path_and_never_falls_back(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path, "# Case: x\n\n**Task prompt:**\n\nplain text\n\n> late quote\n")
        with pytest.raises(ValueError, match=str(path)):
            case_prompt.prompt_for_agent(path)


class TestEveryPromptUnderEvals:
    def test_resolves_and_sends_nothing_of_the_grading_material(self) -> None:
        paths = sorted(_EVALS.glob("*/*/prompt.md"))
        assert len(paths) >= 20
        for path in paths:
            sent = case_prompt.prompt_for_agent(path)
            assert sent.strip(), path
            for forbidden in _FORBIDDEN:
                assert forbidden not in sent, (path, forbidden)
