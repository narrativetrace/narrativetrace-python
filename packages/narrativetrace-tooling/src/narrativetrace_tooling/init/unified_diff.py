# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The smallest unified diff that tells the truth about one file.

INTENT: ``--dry-run`` has to SHOW what would change, and this library takes zero dependencies. The
algorithm is deliberately not Myers: the common prefix and suffix are trimmed and everything between
them is shown as removed-then-added, in one hunk with three lines of context.

**@llmNote** The result is a correct unified diff, not a MINIMAL one. For what the installer
actually edits — a delimited section inside a file, or a page it rewrites whole — the trimmed middle
IS the change. Trading minimality away buys a diff with no quadratic table in it, which is what
makes this safe on a file of any size.

**@llmNote** A line keeps a carriage return it had, so a change of line endings shows as a changed
line rather than as nothing at all.
"""

from __future__ import annotations

from typing import Final

from narrativetrace_tooling.init import marked_block

_CONTEXT: Final = 3

_NO_NEWLINE: Final = "\\ No newline at end of file"


def render_unified_diff(path: str, before: str, after: str) -> str:
    """The diff of one file, or ``""`` when the two texts are equal.

    :param path: the label both sides are named with
    :param before: the whole file before, ``""`` when it did not exist
    :param after: the whole file after, ``""`` when it is being deleted
    """
    if before == after:
        return ""
    old = _lines(before)
    new = _lines(after)
    prefix = _common_prefix(old, new)
    suffix = _common_suffix(old, new, prefix)
    head = [
        f"--- {'/dev/null' if not before else 'a/' + path}",
        f"+++ {'/dev/null' if not after else 'b/' + path}",
    ]
    return "".join(f"{line}\n" for line in head + _hunk(old, new, prefix, suffix, before, after))


def _hunk(
    old: list[str], new: list[str], prefix: int, suffix: int, before: str, after: str
) -> list[str]:
    start = max(0, prefix - _CONTEXT)
    old_end = min(len(old), len(old) - suffix + _CONTEXT)
    new_end = min(len(new), len(new) - suffix + _CONTEXT)
    old_span = _span(start, old_end - start, not old)
    new_span = _span(start, new_end - start, not new)
    header = f"@@ -{old_span} +{new_span} @@"
    return [
        header,
        *(f" {line}" for line in old[start:prefix]),
        *_side(old, prefix, len(old) - suffix, "-", before),
        *_side(new, prefix, len(new) - suffix, "+", after),
        *(f" {line}" for line in old[len(old) - suffix : old_end]),
    ]


def _span(start: int, count: int, empty: bool) -> str:
    """The ``start,count`` half of a hunk header: a side with no lines starts at 0."""
    return "0,0" if empty else f"{start + 1},{count}"


def _side(lines: list[str], first: int, last: int, sign: str, text: str) -> list[str]:
    out: list[str] = []
    for index in range(first, last):
        out.append(f"{sign}{lines[index]}")
        if index == len(lines) - 1 and not text.endswith("\n"):
            out.append(_NO_NEWLINE)
    return out


def _lines(text: str) -> list[str]:
    """Lines without their newline; a carriage return stays, so an ending change is visible."""
    return [
        line[:-1] if line.endswith("\n") else line
        for line in marked_block.split_keeping_terminators(text)
    ]


def _common_prefix(old: list[str], new: list[str]) -> int:
    index = 0
    while index < len(old) and index < len(new) and old[index] == new[index]:
        index += 1
    return index


def _common_suffix(old: list[str], new: list[str], prefix: int) -> int:
    """How many trailing lines match, never reaching back past what the prefix already claimed.

    **@llmNote** The two bounds are what keeps an inserted line identical to its neighbour from
    being counted on both sides at once.
    """
    index = 0
    while (
        index < len(old) - prefix
        and index < len(new) - prefix
        and old[len(old) - 1 - index] == new[len(new) - 1 - index]
    ):
        index += 1
    return index
