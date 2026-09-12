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
from narrativetrace.output.structural_delta import Kind, ScenarioDelta

_HIGH_THRESHOLD = 0.7
_MODERATE_THRESHOLD = 0.4
_SCENARIO_NAME_CAP = 32


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

    def format_delta_line(self, deltas: list[ScenarioDelta]) -> str:
        """One line summarizing every scenario's structural status against its last-green
        artifact, e.g. ``4 scenarios unchanged · 1 changed: "Weekend trip…" (+4 calls
        CurrencyConverter.toBaseCurrency)``. Empty when ``deltas`` is empty."""
        unchanged = sum(1 for d in deltas if d.kind is Kind.UNCHANGED)
        fresh = sum(1 for d in deltas if d.kind is Kind.NEW)
        changed = [d for d in deltas if d.kind is Kind.CHANGED]
        segments: list[str] = []
        if unchanged > 0:
            segments.append(f"{_with_noun(segments, unchanged)} unchanged")
        if fresh > 0:
            segments.append(f"{_with_noun(segments, fresh)} new")
        if changed:
            described = _describe_changed(changed)
            segments.append(f"{_with_noun(segments, len(changed))} changed: {described}")
        return " · ".join(segments)

    def format_failure_report(
        self, scenario: str, trace_text: str, delta: ScenarioDelta | None = None
    ) -> str:
        """A failing test's report — localizes change instead of dumping the trace when the
        failing scenario's structure CHANGED since last green (assertion output already covers
        detection; the trace's job here is saying *where* behavior moved), and says so plainly
        when the structure held (UNCHANGED) so a reader looks at values and assertions instead."""
        if delta is not None and delta.kind is Kind.CHANGED:
            return f"\n\n{scenario}\n\nChanged since last green ({delta.summary}):\n{delta.diff}"
        if delta is not None and delta.kind is Kind.UNCHANGED:
            return (
                f"\n\n{scenario}\n\nStructure unchanged since last green — the flow held; "
                f"check values and assertions.\n\nExecution trace:\n{trace_text}"
            )
        return f"\n\n{scenario}\n\nExecution trace:\n{trace_text}"


def _with_noun(segments: list[str], count: int) -> str:
    """The word "scenario(s)" rides on the first segment only: ``4 scenarios unchanged · 1 new``."""
    if segments:
        return str(count)
    return f"{count} {'scenario' if count == 1 else 'scenarios'}"


def _describe_changed(changed: list[ScenarioDelta]) -> str:
    return ", ".join(f'"{_truncate(d.scenario)}" ({d.summary})' for d in changed)


def _truncate(scenario: str) -> str:
    """Scenario names are capped so one changed scenario cannot flood the one-line summary."""
    if len(scenario) <= _SCENARIO_NAME_CAP:
        return scenario
    return scenario[:_SCENARIO_NAME_CAP].rstrip() + "…"


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
