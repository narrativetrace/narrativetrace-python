# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the library tour: both scenarios run, and the values narrate themselves."""

from __future__ import annotations

import io
from datetime import date

import pytest

from examples.library.library import (
    BookNotFoundError,
    BookUnavailableError,
    build_lending,
    capture_book_unavailable,
    capture_successful_borrow,
    run_example,
    scenarios,
)
from examples.tour import Scenario
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, Returned, Threw


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: str(s.title))
def test_every_scenario_carries_a_wiring_note_and_runs(scenario: Scenario) -> None:
    assert scenario.wiring.startswith("Wiring: ")
    assert not scenario.run(ContextVarNarrativeContext()).is_empty


def test_values_render_through_their_narrative_summary() -> None:
    context = ContextVarNarrativeContext()
    build_lending(context, today=lambda: date(2026, 8, 27)).borrow_book(
        "M-001", "978-0-13-468599-1"
    )
    text = IndentedTextRenderer().render(context.capture_trace())
    assert "→ The Pragmatic Programmer by David Thomas & Andrew Hunt" in text
    assert "→ Alice" in text
    assert "→ The Pragmatic Programmer loaned to Alice, due 2026-09-10" in text
    assert "// Borrowing book 978-0-13-468599-1 for member M-001" in text


def test_the_card_number_never_reaches_the_trace() -> None:
    tree = capture_successful_borrow(ContextVarNarrativeContext())
    lookup = next(n for n in tree.roots[0].children if n.signature.method_name == "lookup_member")
    card = next(p for p in lookup.signature.parameters if p.name == "card_number")
    assert card.redacted
    assert "CARD-VERIFY" not in IndentedTextRenderer().render(tree)


def test_an_unavailable_book_fails_after_the_catalog_lookup() -> None:
    tree = capture_book_unavailable(ContextVarNarrativeContext())
    root = tree.roots[0]
    assert isinstance(root.outcome, Threw)
    assert isinstance(root.outcome.exception, BookUnavailableError)
    assert [n.signature.method_name for n in root.children] == ["find_book"]
    assert isinstance(root.children[0].outcome, Returned)


def test_an_unknown_isbn_carries_the_catalog_error_context() -> None:
    # Not "...-0": an all-zero digit string is Luhn-valid (the checksum's degenerate case), so it
    # would collide with the PAN value-shape detector and redact as a false positive -- an
    # accepted, documented trade-off of that detector, not something this fixture should trigger.
    context = ContextVarNarrativeContext()
    with pytest.raises(BookNotFoundError):
        build_lending(context).borrow_book("M-001", "000-0-00-000000-1")
    lookup = context.capture_trace().roots[0].children[0]
    assert lookup.signature.error_context == "Book 000-0-00-000000-1 not found in catalog"


def test_run_example_prints_both_scenarios_with_the_diagram_sections() -> None:
    out = io.StringIO()
    run_example(out)
    text = out.getvalue()
    headers = [line for line in text.splitlines() if line.startswith("=== ")]
    assert headers == [f"=== {s.title} ===" for s in scenarios()]
    assert "--- PlantUML ---" in text
    assert "!! LendingService.borrow_book ✖ BookUnavailableError" in text
