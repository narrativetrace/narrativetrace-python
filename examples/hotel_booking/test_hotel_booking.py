# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the clarity tour: every scenario runs, and the tiers score the way the tour claims."""

from __future__ import annotations

import io

import pytest
from narrativetrace_clarity import Severity, analyze

from examples.hotel_booking.hotel_booking import (
    EXTRA_WIRING,
    REPORT_BANNER,
    REPORT_LABELS,
    capture_booking_manager,
    capture_guest_repository,
    capture_legacy_processing,
    capture_reservation,
    run_example,
    scenarios,
)
from examples.tour import Scenario
from narrativetrace import ContextVarNarrativeContext


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: str(s.title))
def test_every_scenario_carries_a_wiring_note_and_runs(scenario: Scenario) -> None:
    assert scenario.wiring.startswith("Wiring: ")
    assert not scenario.run(ContextVarNarrativeContext()).is_empty


def test_every_scenario_has_a_report_label_and_the_report_banner_has_a_note() -> None:
    assert set(REPORT_LABELS) == {s.title for s in scenarios()}
    assert EXTRA_WIRING[REPORT_BANNER].startswith("Wiring: ")


def test_the_tiers_score_in_descending_order() -> None:
    excellent = analyze(capture_reservation(ContextVarNarrativeContext())).overall_score
    adequate = analyze(capture_booking_manager(ContextVarNarrativeContext())).overall_score
    poor = analyze(capture_legacy_processing(ContextVarNarrativeContext())).overall_score
    assert excellent > adequate > poor
    assert excellent >= 0.9
    assert poor < 0.5


def test_legacy_processing_is_flagged_high_severity() -> None:
    result = analyze(capture_legacy_processing(ContextVarNarrativeContext()))
    high = {i.category for i in result.issues if i.severity is Severity.HIGH}
    assert high & {"class-name", "method-name"}


def test_guest_repository_trace_holds_the_three_unrelated_calls() -> None:
    tree = capture_guest_repository(ContextVarNarrativeContext())
    assert [n.signature.method_name for n in tree.roots] == [
        "find_guest_by_id",
        "render_report",
        "dispatch_email",
    ]


def test_run_example_prints_the_tiers_then_the_clarity_report() -> None:
    out = io.StringIO()
    run_example(out)
    text = out.getvalue()
    headers = [line for line in text.splitlines() if line.startswith("=== ")]
    assert headers == [f"=== {s.title} ===" for s in scenarios()]
    assert text.index(REPORT_BANNER) > text.index(headers[-1])
    for label in REPORT_LABELS.values():
        assert label in text
    assert "Suite" in text or "suite" in text
