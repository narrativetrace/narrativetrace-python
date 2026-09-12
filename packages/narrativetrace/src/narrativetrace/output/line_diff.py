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


def is_subsequence(baseline: str, current: str) -> bool:
    """True when every line of ``current`` appears in ``baseline``, in order — i.e. ``current``
    differs from ``baseline`` only by omission.

    The question to ask of a run known to be incomplete: equality would fail on the absences the
    best-effort path caused; containment tolerates exactly those and nothing else, so an added,
    renamed or reordered line still comes back ``False``.
    """
    baseline_lines = baseline.splitlines()
    current_lines = current.splitlines()
    matched = 0
    for line in baseline_lines:
        if matched < len(current_lines) and current_lines[matched] == line:
            matched += 1
    return matched == len(current_lines)


def unified(baseline: str, current: str) -> str:
    """The full-document line diff: no hunk elision, since a structural artifact is one test
    scenario and stays small enough to read in full."""
    baseline_lines = baseline.splitlines()
    current_lines = current.splitlines()
    table = _lcs_table(baseline_lines, current_lines)
    return _render(table, baseline_lines, current_lines)


def _lcs_table(baseline: list[str], current: list[str]) -> list[list[int]]:
    table = [[0] * (len(current) + 1) for _ in range(len(baseline) + 1)]
    for i in range(len(baseline) - 1, -1, -1):
        for j in range(len(current) - 1, -1, -1):
            if baseline[i] == current[j]:
                table[i][j] = table[i + 1][j + 1] + 1
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])
    return table


def _render(table: list[list[int]], baseline: list[str], current: list[str]) -> str:
    parts: list[str] = []
    i = j = 0
    while i < len(baseline) and j < len(current):
        if baseline[i] == current[j]:
            parts.append(f" {baseline[i]}\n")
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            parts.append(f"-{baseline[i]}\n")
            i += 1
        else:
            parts.append(f"+{current[j]}\n")
            j += 1
    while i < len(baseline):
        parts.append(f"-{baseline[i]}\n")
        i += 1
    while j < len(current):
        parts.append(f"+{current[j]}\n")
        j += 1
    return "".join(parts)
