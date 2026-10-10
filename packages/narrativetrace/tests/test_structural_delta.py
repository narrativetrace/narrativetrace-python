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


_WITH_IDS = (
    "scenario: Weekend trip settles with three transfers\n"
    "\n"
    "#1 - TripSettlementService.recordExpense(tripName, expense)\n"
    "  #1.1 - ExpenseValidator.ensureValid(expense)\n"
    "  #1.2 - TripLedger.recordExpense(tripName, expense)\n"
)

_WITHOUT_IDS = (
    "scenario: Weekend trip settles with three transfers\n"
    "\n"
    "- TripSettlementService.recordExpense(tripName, expense)\n"
    "  - ExpenseValidator.ensureValid(expense)\n"
    "  - TripLedger.recordExpense(tripName, expense)\n"
)


class TestSpanIdsAreSetAside:
    """Sameness is line equality with span ids, line terminators and a final newline set aside —
    ids are derived from position, so an id-free baseline written before ids existed still
    compares."""

    def test_a_baseline_written_before_span_ids_still_compares_unchanged(self) -> None:
        delta = StructuralDelta(_WITHOUT_IDS, _WITH_IDS)
        assert delta.unchanged is True
        assert delta.summary() == ""
        assert delta.diff() == ""

    def test_the_diff_cites_each_side_by_its_own_span_ids(self) -> None:
        current = _WITH_IDS.replace(
            "  #1.1 - ExpenseValidator.ensureValid(expense)\n",
            "  #1.1 - PolicyEngine.approve(expense) → value\n"
            "  #1.2 - ExpenseValidator.ensureValid(expense)\n",
        ).replace("  #1.2 - TripLedger", "  #1.3 - TripLedger")

        assert StructuralDelta(_WITH_IDS, current).diff() == (
            " scenario: Weekend trip settles with three transfers\n"
            " \n"
            " #1 - TripSettlementService.recordExpense(tripName, expense)\n"
            "+  #1.1 - PolicyEngine.approve(expense) → value\n"
            "   #1.2 - ExpenseValidator.ensureValid(expense)  (was #1.1)\n"
            "   #1.3 - TripLedger.recordExpense(tripName, expense)  (was #1.2)\n"
        )

    def test_removed_and_added_lines_print_as_their_own_side_wrote_them(self) -> None:
        current = _WITH_IDS.replace("  #1.2 - TripLedger", "  #1.2 - Ledger")
        diff = StructuralDelta(_WITH_IDS, current).diff()
        assert diff.splitlines()[-2:] == [
            "-  #1.2 - TripLedger.recordExpense(tripName, expense)",
            "+  #1.2 - Ledger.recordExpense(tripName, expense)",
        ]

    def test_an_id_free_baseline_has_no_id_to_cite_on_a_context_line(self) -> None:
        current = _WITH_IDS + "  #1.3 - Audit.log()\n"
        diff = StructuralDelta(_WITHOUT_IDS, current).diff()
        assert "(was" not in diff
        assert " #1 - TripSettlementService.recordExpense(tripName, expense)\n" in diff

    def test_the_summary_counts_calls_on_lines_that_open_with_ids(self) -> None:
        current = _WITH_IDS + "  ~ fork [2]\n    #1.3 - Pay.charge()\n    #1.4 - Pay.charge()\n"
        assert StructuralDelta(_WITH_IDS, current).summary() == "+2 calls Pay.charge"

    def test_a_baseline_without_its_final_newline_is_unchanged(self) -> None:
        delta = StructuralDelta("scenario: s\n\n- A.a()\n", "scenario: s\n\n- A.a()")
        assert delta.unchanged is True
        assert delta.diff() == ""

    def test_a_baseline_checked_out_with_crlf_line_endings_is_unchanged(self) -> None:
        delta = StructuralDelta("scenario: s\r\n\r\n#1 - A.a()\r\n", "scenario: s\n\n#1 - A.a()\n")
        assert delta.unchanged is True
        assert delta.diff() == ""
        assert delta.only_omits() is True

    def test_a_form_feed_or_line_separator_inside_a_line_does_not_split_it(self) -> None:
        # Lines end at LF, CR or CRLF only — as the reference runtime reads them. str.splitlines
        # would also split here and call two different documents the same.
        baseline = "scenario: s\n\n- A.a\x0cb()\n"
        current = "scenario: s\n\n- A.a\n- b()\n"
        assert StructuralDelta(baseline, current).unchanged is False
        assert StructuralDelta("- A.a\u2028b()\n", "- A.a\n- b()\n").unchanged is False

    def test_a_trailing_space_is_still_a_change(self) -> None:
        assert StructuralDelta("#1 - A.a()\n", "#1 - A.a() \n").unchanged is False

    def test_a_malformed_id_is_not_set_aside(self) -> None:
        assert StructuralDelta("- A.a()\n", "#1. - A.a()\n").unchanged is False


class TestOnlyOmits:
    _BASE = "scenario: s\n\n#1 - A.a()\n  #1.1 - B.b()\n  #1.2 - C.c()\n"

    def test_an_omission_that_shifts_later_ids_only_omits(self) -> None:
        delta = StructuralDelta(self._BASE, "scenario: s\n\n#1 - A.a()\n  #1.1 - C.c()\n")
        assert delta.only_omits() is True
        assert delta.summary() == "-1 call B.b"

    def test_an_added_line_is_not_an_omission(self) -> None:
        current = "scenario: s\n\n#1 - A.a()\n  #1.1 - X.x()\n  #1.2 - B.b()\n"
        baseline = "scenario: s\n\n#1 - A.a()\n  #1.1 - B.b()\n"
        assert StructuralDelta(baseline, current).only_omits() is False

    def test_two_reordered_lines_are_not_an_omission(self) -> None:
        current = "scenario: s\n\n#1 - A.a()\n  #1.1 - C.c()\n  #1.2 - B.b()\n"
        assert StructuralDelta(self._BASE, current).only_omits() is False
