# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The delimited section the installer owns inside a consumer's file, and every edit that section
can undergo.

INTENT: one place decides what counts as a marker. Everything the installer writes into a file it
did not create lives between ``<!-- narrativetrace:start … -->`` and
``<!-- narrativetrace:end -->``, so a re-run replaces exactly that region and an uninstall removes
exactly that region — the property that makes both operations safe on a file somebody else owns.

**@llmNote** The marker rule is narrow on purpose: a marker counts only when its line STARTS with
the marker text (column 0, no indentation) and the line is OUTSIDE a fenced code block. A document
that shows the markers in an example fence therefore keeps its own meaning, and this repository's
own ``narrativetrace:skills:*`` markers are not consumer markers — the prefix differs.

**@llmNote** :func:`append` and :func:`remove` are inverses: appending separates the block from what
was there with exactly one blank line, and removing takes that blank line back. The one thing an
append cannot undo is the final newline it adds to a file that had none — a block has to start on
its own line.

Internal to :mod:`narrativetrace_tooling.init`; nothing outside the installer reads a marker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

START: Final = "<!-- narrativetrace:start"
"""The opening marker, up to but not including the optional coordinate stamp."""

END: Final = "<!-- narrativetrace:end -->"

CREATED_NOTE: Final = "<!-- narrativetrace:created -->"
"""Written as the first line of a file the installer CREATED, so an uninstall can tell a file it may
delete from one it merely appended to."""

_BOM: Final = "﻿"

_FENCES: Final = ("```", "~~~")


@dataclass(frozen=True, slots=True)
class Region:
    """One managed region inside a file.

    :param start: offset of the first character of the opening marker's line
    :param end: offset just past the closing marker's line, its terminator included
    :param start_line: 1-based line of the opening marker, so a refusal can name it
    :param coordinate: the stamp on the opening marker, ``""`` when it carries none
    """

    start: int
    end: int
    start_line: int
    coordinate: str


@dataclass(frozen=True, slots=True)
class Line:
    """One line of a file, with everything a marker decision needs.

    :param number: 1-based line number
    :param start: offset of the line's first character
    :param end: offset just past the line's terminator
    :param content: the line without its terminator, and without a leading byte-order mark
    :param in_fence: whether the line sits inside a fenced code block
    """

    number: int
    start: int
    end: int
    content: str
    in_fence: bool


@dataclass(frozen=True, slots=True)
class Scan:
    """What a scan found.

    :param regions: complete start/end pairs, in file order
    :param problems: human-readable, line-numbered marker problems — a caller REFUSES a file with
        any of them, rather than guessing which marker was meant
    """

    regions: tuple[Region, ...]
    problems: tuple[str, ...]

    def has_exactly_one_region(self) -> bool:
        """Whether the file carries exactly one well-formed region and nothing questionable."""
        return not self.problems and len(self.regions) == 1


def split_keeping_terminators(text: str) -> tuple[str, ...]:
    """Splits into lines that still carry their terminators, so offsets stay exact."""
    require_text(text)
    lines_out: list[str] = []
    start = 0
    while start < len(text):
        newline = text.find("\n", start)
        end = len(text) if newline < 0 else newline + 1
        lines_out.append(text[start:end])
        start = end
    return tuple(lines_out)


def lines(text: str) -> tuple[Line, ...]:
    """Splits a file into lines that know their offsets and whether they sit inside a fence — the
    one primitive both the marker scan and the import-line check read a file through."""
    require_text(text)
    out: list[Line] = []
    in_fence = False
    offset = 0
    for number, raw in enumerate(split_keeping_terminators(text), start=1):
        content = _content_for_matching(raw, number)
        fence_line = _is_fence(content)
        out.append(Line(number, offset, offset + len(raw), content, in_fence or fence_line))
        in_fence = not in_fence if fence_line else in_fence
        offset += len(raw)
    return tuple(out)


def scan(text: str) -> Scan:
    """Finds every managed region in a file. Never raises: a malformed file is described, not
    read."""
    scanner = _Scanner()
    for line in lines(text):
        if not line.in_fence:
            scanner.accept(line)
    return scanner.finish()


def ends_inside_fence(text: str) -> bool:
    """Whether the text ends with a fenced code block still open.

    **@llmNote** Load-bearing: anything appended to such a file lands INSIDE that fence, where
    neither this scanner nor any Markdown reader will see it as a marker or an import — so the next
    run appends again, and the run after that. Appending to one is refused, not attempted.
    """
    return sum(1 for line in lines(text) if _is_fence(line.content)) % 2 == 1


def line_is(text: str, wanted: str) -> Line | None:
    """The first line outside a fence whose text is exactly this — what an uninstall removes."""
    return _first_line(text, lambda content: content == wanted)


def line_is_ignoring_trailing_space(text: str, wanted: str) -> Line | None:
    """The first line outside a fence whose text, trailing whitespace ignored, is this — what an
    install reads as "already there", because trailing spaces change nothing for a reader."""
    return _first_line(text, lambda content: content.rstrip() == wanted)


def replace(text: str, region: Region, block: str) -> str:
    """Replaces one region with ``block``, byte for byte everywhere else."""
    require_text(text)
    require_text(block)
    return text[: region.start] + block + text[region.end :]


def append(text: str, block: str) -> str:
    """Appends ``block`` to ``text``, separated by exactly one blank line — nothing at all when the
    file is empty. A file that did not end with a newline gets one: a block starts on its own
    line."""
    require_text(text)
    require_text(block)
    if not text:
        return block
    eol = eol_of(text)
    head = text if text.endswith(("\n", "\r")) else text + eol
    return head + eol + block


def remove(text: str, span: Region | Line) -> str:
    """Removes one region or one line, and the single blank line :func:`append` would have put
    before it."""
    require_text(text)
    head = text[: span.start]
    eol = eol_of(text)
    if head.endswith(eol + eol):
        head = head[: -len(eol)]
    return head + text[span.end :]


def eol_of(text: str) -> str:
    """The line ending a file uses, decided by its FIRST terminator; ``\\n`` when it has none."""
    require_text(text)
    newline = text.find("\n")
    if newline < 0:
        return "\n"
    return "\r\n" if newline > 0 and text[newline - 1] == "\r" else "\n"


def with_eol(text: str, eol: str) -> str:
    """The same text with every line ending rewritten to ``eol``."""
    require_text(text)
    require_text(eol)
    return text.replace("\r\n", "\n").replace("\n", eol)


class _Scanner:
    """Walks the lines once, holding the one piece of state a scan needs: the open start marker."""

    def __init__(self) -> None:
        self._regions: list[Region] = []
        self._problems: list[str] = []
        self._open_offset = -1
        self._open_line = 0
        self._open_coordinate = ""

    def accept(self, line: Line) -> None:
        if line.content.startswith(START):
            self._open(line)
        elif line.content.startswith(END):
            self._close(line)

    def finish(self) -> Scan:
        """After the last line: a start that never closed is a problem, not a region."""
        if self._open_offset >= 0:
            self._problems.append(
                f"line {self._open_line}: a narrativetrace:start marker with no end below it"
            )
        return Scan(tuple(self._regions), tuple(self._problems))

    def _open(self, line: Line) -> None:
        if self._open_offset >= 0:
            self._problems.append(
                f"line {line.number}: a narrativetrace:start marker inside the block opened at "
                f"line {self._open_line}"
            )
            return
        self._open_offset = line.start
        self._open_line = line.number
        self._open_coordinate = _coordinate_in(line.content)

    def _close(self, line: Line) -> None:
        if self._open_offset < 0:
            self._problems.append(
                f"line {line.number}: a narrativetrace:end marker with no start above it"
            )
            return
        self._regions.append(
            Region(self._open_offset, line.end, self._open_line, self._open_coordinate)
        )
        self._open_offset = -1


def _coordinate_in(content: str) -> str:
    """The bare coordinate between the marker prefix and the comment's close."""
    rest = content[len(START) :]
    close = rest.find("-->")
    return "" if close < 0 else rest[:close].strip()


def _first_line(text: str, matches: Callable[[str], bool]) -> Line | None:
    return next((line for line in lines(text) if not line.in_fence and matches(line.content)), None)


def _is_fence(content: str) -> bool:
    """A fenced-code delimiter, recognised at column 0 like every other marker here."""
    return content.startswith(_FENCES)


def _content_for_matching(raw: str, number: int) -> str:
    """The line's content for MATCHING only: no terminator, and no byte-order mark on line 1."""
    content = raw[:-1] if raw.endswith("\n") else raw
    content = content[:-1] if content.endswith("\r") else content
    return content[1:] if number == 1 and content.startswith(_BOM) else content


def require_text(text: str) -> None:
    """The installer's one text guard, shared by every module that reads a consumer file.

    ``None`` is the value it exists for: these functions are reached from a reader that answers "the
    file, or nothing", and a missing file slipping through would otherwise surface far away, as a
    ``TypeError`` from a slice in the middle of a scan.
    """
    if not isinstance(text, str):
        raise TypeError(f"a marked block reads text, never {type(text).__name__}")
