# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What the agent is told for a case: the quoted task prompt of a case document, or a bare prompt
file byte for byte.

A ``prompt.md`` is one of two things. A CASE DOCUMENT (its first line starts with ``# Case:``) is
the case's description -- fixture, task prompt, expected trajectory, grading -- and only the
``>`` blockquote under its ``**Task prompt`` line is the user's words. Anything else is a BARE
PROMPT: the words themselves (the init-prompt cases), sent exactly as written.
"""

from __future__ import annotations

from pathlib import Path

_CASE_DOCUMENT_MARKER = "# Case:"
_TASK_PROMPT_MARKER = "**Task prompt"


def is_case_document(prompt_path: Path) -> bool:
    """Whether the first line of ``prompt_path`` starts with ``# Case:``."""
    text = prompt_path.read_text(encoding="utf-8")
    return text.startswith(_CASE_DOCUMENT_MARKER)


def prompt_for_agent(prompt_path: Path) -> str:
    """The text the agent is sent for the case whose prompt file is ``prompt_path``.

    **@llmNote** A bare prompt is returned byte for byte. A case document yields only the
    blockquote directly under its ``**Task prompt`` line (blank lines between the two skipped):
    the ``>`` prefix and one following space are stripped, wrapped lines are joined with one
    space, an empty ``>`` line is a paragraph break, and paragraphs are joined by a blank line.

    :raises ValueError: for a case document with no such blockquote, naming the path. Never a
        fall-back to the whole file: that hands the agent the expected trajectory and the grading.
    """
    text = prompt_path.read_text(encoding="utf-8")
    if not text.startswith(_CASE_DOCUMENT_MARKER):
        return text
    quoted = _quoted_lines_under_the_task_prompt(text.splitlines())
    if not quoted:
        raise ValueError(
            f"{prompt_path} is a case document (its first line starts with "
            f"{_CASE_DOCUMENT_MARKER!r}) but has no '>' blockquote under its "
            f"{_TASK_PROMPT_MARKER}' line, so there is no task prompt to send"
        )
    return _paragraphs(quoted)


def _quoted_lines_under_the_task_prompt(lines: list[str]) -> list[str]:
    marked = [i for i, line in enumerate(lines) if line.startswith(_TASK_PROMPT_MARKER)]
    if not marked:
        return []
    quoted: list[str] = []
    for line in lines[marked[0] + 1 :]:
        if line.startswith(">"):
            quoted.append(_unquoted(line))
        elif quoted or line.strip():
            break
    return quoted


def _unquoted(line: str) -> str:
    body = line[1:]
    return body[1:] if body.startswith(" ") else body


def _paragraphs(quoted: list[str]) -> str:
    paragraphs: list[list[str]] = [[]]
    for line in quoted:
        if line.strip():
            paragraphs[-1].append(line.strip())
        elif paragraphs[-1]:
            paragraphs.append([])
    return "\n\n".join(" ".join(paragraph) for paragraph in paragraphs if paragraph)
