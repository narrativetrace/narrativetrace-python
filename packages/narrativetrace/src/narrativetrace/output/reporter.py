# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Console summary formatting for the pytest plugin.

``ConsoleSummaryReporter``. Keeps the plugin free of formatting details while producing
stable, golden-testable summary strings. Percentages use Java ``Math.round`` (half-up) semantics,
and an empty clarity list yields the ``0% high | 0% moderate | 0% low`` invariant.
"""

from __future__ import annotations

import math

from narrativetrace.loss import TraceLoss

_HIGH_THRESHOLD = 0.7
_MODERATE_THRESHOLD = 0.4


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


class ConsoleSummaryReporter:
    """Formats per-test and suite-level console summaries."""

    def format_test_result(
        self, test_name: str, duration_ms: int, clarity_score: float | None = None
    ) -> str:
        """A passing-test line, optionally including the clarity score."""
        if clarity_score is None:
            return f"    ✓ {test_name} ({duration_ms}ms)"
        return f"    ✓ {test_name} ({duration_ms}ms, clarity: {clarity_score:.2f})"

    def format_test_failure(
        self,
        test_name: str,
        duration_ms: int,
        exception_type: str,
        location: str,
        trace_file_path: str,
    ) -> str:
        """A three-line failing-test block."""
        return (
            f"    ✗ {test_name} ({duration_ms}ms)\n"
            f"      > {exception_type} at {location}\n"
            f"      > Full trace: {trace_file_path}"
        )

    def format_suite_header(self) -> str:
        """The suite header line."""
        return "NarrativeTrace — Recording test narratives\n"

    def format_suite_footer(
        self,
        scenario_count: int,
        output_path: str,
        clarity_scores: list[float] | None = None,
        loss: TraceLoss | None = None,
    ) -> str:
        """The suite footer: a clarity split when scores are supplied, and what the run lost.

        The loss line is omitted entirely at zero loss, so an ordinary footer is unchanged. It is
        there because a short trace must never be indistinguishable from a quiet one: the buffered
        path sheds under load and the adoption cap refuses async scopes, and both are invisible
        without it.
        """
        loss_line = _loss_line(loss)
        if clarity_scores is None:
            return (
                "\nNarrativeTrace — Suite complete\n"
                f"  {scenario_count} scenarios recorded\n"
                f"{loss_line}"
                f"  Reports: {output_path}"
            )
        high = sum(1 for s in clarity_scores if s >= _HIGH_THRESHOLD)
        moderate = sum(1 for s in clarity_scores if _MODERATE_THRESHOLD <= s < _HIGH_THRESHOLD)
        low = len(clarity_scores) - high - moderate
        total = len(clarity_scores)
        high_pct = _round_half_up(100 * high / total) if total else 0
        moderate_pct = _round_half_up(100 * moderate / total) if total else 0
        low_pct = _round_half_up(100 * low / total) if total else 0
        return (
            "\nNarrativeTrace — Suite complete\n"
            f"  {scenario_count} scenarios recorded\n"
            f"  Clarity: {high_pct}% high | {moderate_pct}% moderate | {low_pct}% low\n"
            f"{loss_line}"
            f"  Reports: {output_path}"
        )


def _loss_line(loss: TraceLoss | None) -> str:
    """The ``Incomplete:`` line, or nothing at all when the run lost nothing."""
    if loss is None or not loss.any():
        return ""
    parts = []
    if loss.dropped_events > 0:
        parts.append(f"{_count(loss.dropped_events, 'event')} dropped (buffer full)")
    if loss.refused_scopes > 0:
        parts.append(
            f"{_count(loss.refused_scopes, 'async scope')} not adopted (cap), "
            f"{_count(loss.refused_spans, 'span')}"
        )
    return "  Incomplete: " + ", ".join(parts) + "\n"


def _count(value: int, noun: str) -> str:
    return f"{value} {noun}" if value == 1 else f"{value} {noun}s"
