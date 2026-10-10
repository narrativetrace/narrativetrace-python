# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Longest-common-subsequence line diff in the conventional format: ``-`` removed, ``+`` added,
one leading space on unchanged context lines.

The rendering half of :mod:`narrativetrace.output.structural_delta` — kept free of any ``.nt``
format knowledge so the delta module owns what a change *means* and this one owns how a change
*reads*. Inputs are whole documents; ties between a deletion and an insertion resolve to the
deletion so removed lines always precede their replacements.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_LINE_END = re.compile(r"\r\n|\r|\n")


def lines(document: str) -> list[str]:
    """The document's lines, split at LF, CR or CRLF only and without a final empty line — the
    lines the reference runtime reads. :meth:`str.splitlines` also splits at form feeds, NEL and
    U+2028/U+2029, which would make two different documents look the same."""
    split = _LINE_END.split(document)
    return split[:-1] if split[-1] == "" else split


def _identity(line: str) -> str:
    return line


def _current_side(_was: str, now: str) -> str:
    return now


def is_subsequence(baseline: str, current: str) -> bool:
    """True when every line of ``current`` appears in ``baseline``, in order — i.e. ``current``
    differs from ``baseline`` only by omission.

    The question to ask of a run known to be incomplete: equality would fail on the absences the
    best-effort path caused; containment tolerates exactly those and nothing else, so an added,
    renamed or reordered line still comes back ``False``.
    """
    baseline_lines = lines(baseline)
    current_lines = lines(current)
    matched = 0
    for line in baseline_lines:
        if matched < len(current_lines) and current_lines[matched] == line:
            matched += 1
    return matched == len(current_lines)


def unified(
    baseline: str,
    current: str,
    key: Callable[[str], str] = _identity,
    context: Callable[[str, str], str] = _current_side,
) -> str:
    """The full-document line diff: no hunk elision, since a structural artifact is one test
    scenario and stays small enough to read in full.

    Lines are matched on ``key``, so two lines whose keys agree are context even when their bytes
    differ; ``context`` renders such a pair from (baseline line, current line). Removed lines print
    as the baseline wrote them, added lines as the current document does.
    """
    sides = _Sides(lines(baseline), lines(current), key)
    table = _lcs_table(sides.baseline_keys, sides.current_keys)
    return _render(table, sides, context)


class _Sides:
    """Both documents, each as its printed lines and the keys those lines are matched on."""

    def __init__(self, baseline: list[str], current: list[str], key: Callable[[str], str]) -> None:
        self.baseline = baseline
        self.current = current
        self.baseline_keys = [key(line) for line in baseline]
        self.current_keys = [key(line) for line in current]


def _lcs_table(baseline: list[str], current: list[str]) -> list[list[int]]:
    table = [[0] * (len(current) + 1) for _ in range(len(baseline) + 1)]
    for i in range(len(baseline) - 1, -1, -1):
        for j in range(len(current) - 1, -1, -1):
            if baseline[i] == current[j]:
                table[i][j] = table[i + 1][j + 1] + 1
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])
    return table


def _render(table: list[list[int]], sides: _Sides, context: Callable[[str, str], str]) -> str:
    baseline, current = sides.baseline, sides.current
    parts: list[str] = []
    i = j = 0
    while i < len(baseline) and j < len(current):
        if sides.baseline_keys[i] == sides.current_keys[j]:
            parts.append(f" {context(baseline[i], current[j])}\n")
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            parts.append(f"-{baseline[i]}\n")
            i += 1
        else:
            parts.append(f"+{current[j]}\n")
            j += 1
    parts.extend(f"-{line}\n" for line in baseline[i:])
    parts.extend(f"+{line}\n" for line in current[j:])
    return "".join(parts)
