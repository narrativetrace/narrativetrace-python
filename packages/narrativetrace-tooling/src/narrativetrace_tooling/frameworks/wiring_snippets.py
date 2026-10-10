# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The wiring lines of every source-wired framework row, read from ``wiring-snippets.md`` shipped
inside this library.

INTENT: the doctor's fix must carry the exact lines a project adds, and those lines must never be
typed — they are a fixture's the suite runs. The resource holds one ``## <row id>`` section per row,
each wrapping a fenced block in the same ``<!-- snippet: path region=… -->`` markers the
documentation uses, so ``poe snippet-sync`` writes the fixture's current text into it and ``poe
snippet-check`` fails the build when the two drift. The wheel then carries the text to wherever the
doctor runs, with no repository in sight. Mirrors Java's ``WiringSnippets``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources
from types import MappingProxyType
from typing import Final

RESOURCE: Final = "wiring-snippets.md"
"""The resource's name, beside this module."""

_HEADING: Final = "## "
_FENCE: Final = "```"
_MARKER_OPEN: Final = "<!-- snippet:"
_MARKER_CLOSE: Final = "-->"


@dataclass(frozen=True, slots=True)
class Entry:
    """One row's snippet: the fixture its marker names, its region (``None`` for a whole file),
    and the fenced block's body, each line ending in a newline."""

    fixture: str
    region: str | None
    body: str


@cache
def entries() -> MappingProxyType[str, Entry]:
    """Every section, by row id, in document order — read once per process."""
    markdown = resources.files(__package__).joinpath(RESOURCE).read_text(encoding="utf-8")
    return MappingProxyType(parse(markdown))


def text(row_id: str) -> str:
    """The wiring lines of the row with this id.

    :raises LookupError: when the resource has no section for the row — a table row without its
        snippet is a build defect the drift tests exist to catch, never a runtime case.
    """
    entry = entries().get(row_id)
    if entry is None:
        raise LookupError(f"{RESOURCE} has no section for row {row_id}")
    return entry.body


def parse(markdown: str) -> dict[str, Entry]:
    """Each ``## id`` section's snippet marker and the fenced block right after it. A fenced block
    is skipped whole wherever it appears, so a heading INSIDE one is body, never a new section.
    Line-based on purpose — no pattern walks the document; CRLF line endings read as LF, so a
    checkout that converted them never carries a carriage return into a fix line."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    parsed: dict[str, Entry] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(_FENCE):
            i = _closing_fence(lines, i + 1) + 1
        elif line.startswith(_HEADING):
            i = _read_section(lines, i + 1, line[len(_HEADING) :].strip(), parsed)
        else:
            i += 1
    return parsed


def _read_section(lines: list[str], start: int, row_id: str, parsed: dict[str, Entry]) -> int:
    """Reads one section up to its marked block, recording the entry; returns where the scan
    resumes — after the block, or at the first heading or unmarked fence."""
    i = start
    while i < len(lines) and not lines[i].startswith((_HEADING, _FENCE)):
        if lines[i].startswith(_MARKER_OPEN) and i + 1 < len(lines):
            return _read_block(lines, i, row_id, parsed)
        i += 1
    return i


def _read_block(lines: list[str], marker: int, row_id: str, parsed: dict[str, Entry]) -> int:
    if not lines[marker + 1].startswith(_FENCE):
        return marker + 1
    close = _closing_fence(lines, marker + 2)
    target = _marker_target(lines[marker])
    if close >= len(lines) or target is None:
        return close + 1
    fixture, region = target
    body = "".join(line + "\n" for line in lines[marker + 2 : close])
    parsed[row_id] = Entry(fixture, region, body)
    return close + 1


def _closing_fence(lines: list[str], start: int) -> int:
    i = start
    while i < len(lines) and lines[i].rstrip() != _FENCE:
        i += 1
    return i


def _marker_target(marker: str) -> tuple[str, str | None] | None:
    """The marker's fixture path and region, or ``None`` for a marker that names no path."""
    tokens = marker[len(_MARKER_OPEN) :].replace(_MARKER_CLOSE, " ").split()
    if not tokens:
        return None
    options = dict(token.split("=", 1) for token in tokens[1:] if "=" in token)
    return tokens[0], options.get("region")
