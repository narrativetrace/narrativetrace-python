# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one line that says a copied ``SKILL.md`` is ours, and which carrier it came from.

INTENT: the installer must be able to tell a page it wrote from a page somebody else wrote, years
later and with no other state. That is what makes an upgrade safe (overwrite ours), a foreign
directory safe (refuse), and an uninstall safe (delete only ours).

**@llmNote** The line goes AFTER the YAML frontmatter, never before it: a comment above the opening
``---`` stops the frontmatter from parsing, and every skill runtime reads that frontmatter first.

**@llmNote** Matching is anchored at column 0, the same rule the managed block's markers follow, so
a page that quotes the line in an example is not mistaken for an installed page.

Internal to :mod:`narrativetrace_tooling.init`.
"""

from __future__ import annotations

from typing import Final

from narrativetrace_tooling.init import marked_block

PREFIX: Final = "<!-- installed by narrativetrace init from "

SUFFIX: Final = " — edit the catalogue, not this file -->"

_FRONTMATTER_FENCE: Final = "---"


def line(coordinate: str) -> str:
    """The provenance line for one carrier coordinate.

    :param coordinate: this runtime's own form, a PEP 440 pin — ``narrativetrace-skills==1.2.3``
    :raises ValueError: when the coordinate is blank; a page stamped with nothing is a page nothing
        can tell apart from somebody else's
    """
    _require_coordinate(coordinate)
    return PREFIX + coordinate + SUFFIX


def coordinate_in(page: str) -> str | None:
    """The coordinate a page was installed from, or ``None`` when the page is not ours."""
    marked_block.require_text(page)
    for raw in marked_block.split_keeping_terminators(page):
        coordinate = _coordinate_of(_content(raw))
        if coordinate is not None:
            return coordinate
    return None


def stamp(page: str, coordinate: str) -> str:
    """The page with exactly one provenance line for ``coordinate``, placed after the frontmatter —
    replacing any line a previous install left, so stamping twice is stamping once."""
    _require_coordinate(coordinate)
    marked_block.require_text(page)
    eol = marked_block.eol_of(page)
    insert_after = _frontmatter_end(page)
    out: list[str] = []
    for number, raw in enumerate(marked_block.split_keeping_terminators(page), start=1):
        if not _is_provenance(_content(raw)):
            out.append(raw)
        if number == insert_after:
            out.append(line(coordinate) + eol)
    body = "".join(out)
    stamped = line(coordinate) + eol + eol + body if insert_after == 0 else body
    assert coordinate_in(stamped) == coordinate.strip(), "a stamped page reads its coordinate back"
    return stamped


def _coordinate_of(text: str) -> str | None:
    """The coordinate one line carries, or ``None`` when the line is not a provenance line."""
    if not _is_provenance(text):
        return None
    coordinate = text[len(PREFIX) : len(text) - len(SUFFIX)].strip()
    return coordinate or None


def _is_provenance(text: str) -> bool:
    """A whole line, not a fragment.

    **@llmNote** The length guard matters: :data:`PREFIX` ends with a space and :data:`SUFFIX`
    starts with one, so the two can OVERLAP in a hand-edited line and a bare startswith/endswith
    pair would then read a coordinate out of a line that names none.
    """
    return (
        len(text) >= len(PREFIX) + len(SUFFIX) and text.startswith(PREFIX) and text.endswith(SUFFIX)
    )


def _frontmatter_end(page: str) -> int:
    """The 1-based line number of the frontmatter's closing fence, or 0 when there is none."""
    lines = marked_block.split_keeping_terminators(page)
    if not lines or _content(lines[0]) != _FRONTMATTER_FENCE:
        return 0
    for index in range(1, len(lines)):
        if _content(lines[index]) == _FRONTMATTER_FENCE:
            return index + 1
    return 0


def _content(raw: str) -> str:
    """A line without its terminator."""
    text = raw[:-1] if raw.endswith("\n") else raw
    return text[:-1] if text.endswith("\r") else text


def _require_coordinate(coordinate: str) -> None:
    if not isinstance(coordinate, str) or not coordinate.strip():
        raise ValueError("a provenance line names the carrier it came from, and this one is blank")
