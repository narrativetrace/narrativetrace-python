# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for :mod:`narrativetrace.output.structural_delta` and
:mod:`narrativetrace.output.line_diff` — pinned byte-for-byte against the reference format's
``StructuralDeltaTest`` assertions.
"""

from __future__ import annotations

from narrativetrace.output import line_diff
from narrativetrace.output.structural_delta import Kind, ScenarioDelta, StructuralDelta

_BASELINE = (
    "scenario: Weekend trip settles with three transfers\n"
    "\n"
    "- TripSettlementService.recordExpense(tripName, expense)\n"
    "  - ExpenseValidator.ensureValid(expense)\n"
    "  - TripLedger.recordExpense(tripName, expense)\n"
    "- TripSettlementService.settleTrip(tripName) → value\n"
    "  - TripLedger.expensesOf(tripName) → value\n"
    "  - BalanceCalculator.computeBalances(expenses) → value\n"
)


class TestUnchanged:
    def test_identical_documents_are_unchanged(self) -> None:
        delta = StructuralDelta(_BASELINE, _BASELINE)
        assert delta.unchanged is True
        assert delta.summary() == ""
        assert delta.diff() == ""


class TestSummary:
    def test_an_added_call_is_reported_as_plus_one(self) -> None:
        current = _BASELINE + "  - CurrencyConverter.toBaseCurrency(amount)\n"
        delta = StructuralDelta(_BASELINE, current)
        assert delta.summary() == "+1 call CurrencyConverter.toBaseCurrency"

    def test_four_added_calls_pluralize_the_noun(self) -> None:
        addition = "  - CurrencyConverter.toBaseCurrency(amount)\n" * 4
        delta = StructuralDelta(_BASELINE, _BASELINE + addition)
        assert delta.summary() == "+4 calls CurrencyConverter.toBaseCurrency"

    def test_a_removed_call_is_reported_as_minus_one(self) -> None:
        current = _BASELINE.replace("  - ExpenseValidator.ensureValid(expense)\n", "")
        delta = StructuralDelta(_BASELINE, current)
        assert delta.summary() == "-1 call ExpenseValidator.ensureValid"

    def test_mixed_changes_list_added_signatures_before_removed_ones(self) -> None:
        current = _BASELINE.replace(
            "  - ExpenseValidator.ensureValid(expense)\n",
            "  - PolicyEngine.approve(expense)\n",
        )
        delta = StructuralDelta(_BASELINE, current)
        assert delta.summary() == (
            "+1 call PolicyEngine.approve, -1 call ExpenseValidator.ensureValid"
        )

    def test_same_call_count_but_different_shape_falls_back_to_structure_changed(self) -> None:
        current = _BASELINE.replace(
            "  - ExpenseValidator.ensureValid(expense)\n",
            "  - ExpenseValidator.ensureValid(expense) !! InvalidExpenseException\n",
        )
        delta = StructuralDelta(_BASELINE, current)
        assert delta.summary() == "structure changed"


class TestDiff:
    def test_unchanged_lines_carry_one_leading_space(self) -> None:
        current = _BASELINE + "  - CurrencyConverter.toBaseCurrency(amount)\n"
        rendered = StructuralDelta(_BASELINE, current).diff()
        assert " - TripSettlementService.recordExpense(tripName, expense)\n" in rendered

    def test_an_added_line_is_prefixed_with_plus(self) -> None:
        current = _BASELINE + "  - CurrencyConverter.toBaseCurrency(amount)\n"
        rendered = StructuralDelta(_BASELINE, current).diff()
        assert "+  - CurrencyConverter.toBaseCurrency(amount)\n" in rendered

    def test_a_removed_line_is_prefixed_with_minus(self) -> None:
        current = _BASELINE.replace("  - ExpenseValidator.ensureValid(expense)\n", "")
        rendered = StructuralDelta(_BASELINE, current).diff()
        assert "-  - ExpenseValidator.ensureValid(expense)\n" in rendered


class TestScenarioDelta:
    def test_no_baseline_is_new(self) -> None:
        delta = ScenarioDelta.of("scenario", None, _BASELINE)
        assert delta.kind is Kind.NEW
        assert delta.summary == ""
        assert delta.diff == ""

    def test_identical_current_is_unchanged(self) -> None:
        delta = ScenarioDelta.of("scenario", _BASELINE, _BASELINE)
        assert delta.kind is Kind.UNCHANGED

    def test_different_current_is_changed_and_carries_summary_and_diff(self) -> None:
        current = _BASELINE + "  - CurrencyConverter.toBaseCurrency(amount)\n"
        delta = ScenarioDelta.of("scenario", _BASELINE, current)
        assert delta.kind is Kind.CHANGED
        assert delta.summary == "+1 call CurrencyConverter.toBaseCurrency"
        assert delta.diff != ""


class TestLineDiffSubsequence:
    def test_current_that_omits_lines_is_a_subsequence(self) -> None:
        current = _BASELINE.replace("  - ExpenseValidator.ensureValid(expense)\n", "")
        assert line_diff.is_subsequence(_BASELINE, current) is True

    def test_current_with_an_added_line_is_not_a_subsequence(self) -> None:
        current = _BASELINE + "  - CurrencyConverter.toBaseCurrency(amount)\n"
        assert line_diff.is_subsequence(_BASELINE, current) is False

    def test_current_with_a_reordered_line_is_not_a_subsequence(self) -> None:
        lines = _BASELINE.splitlines()
        reordered = "\n".join([lines[0], lines[2], lines[1], *lines[3:]]) + "\n"
        assert line_diff.is_subsequence(_BASELINE, reordered) is False

    def test_identical_documents_are_a_subsequence_of_each_other(self) -> None:
        assert line_diff.is_subsequence(_BASELINE, _BASELINE) is True
