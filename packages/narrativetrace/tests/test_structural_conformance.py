# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Cross-platform conformance: the ``.nt`` format is normative and shared by every NarrativeTrace
runtime, because these files are the approval baselines and conformance fixtures that travel
between platforms. This pins the Python renderer against a golden fixture from the reference
format — byte for byte, the same fixture the .NET runtime pins its own renderer against.

Mirrors ``StructuralTraceConformanceTests`` (the cross-port pattern named in the port's own
backlog: "pin the renderer byte-for-byte against a Java-produced golden ... never regenerate the
golden from Python").
"""

from __future__ import annotations

from pathlib import Path

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.render.structural import StructuralTraceRenderer
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree

_FIXTURES = Path(__file__).parent / "fixtures"


class InvalidExpenseException(Exception):
    """The exception the reference scenario throws — named to match, because the artifact records
    the exception's simple type name as structure."""


def _call(
    class_name: str,
    method_name: str,
    parameters: list[str],
    outcome: Returned | Threw,
    children: list[TraceNode] | None = None,
) -> TraceNode:
    captures = [ParameterCapture(name, '"redacted-by-design"') for name in parameters]
    return TraceNode(
        signature=MethodSignature(class_name, method_name, captures),
        children=children or [],
        outcome=outcome,
        duration_nanos=7_000_000,
    )


def _fair_split_negative_expense() -> TraceTree:
    """The ``fairsplit`` dogfood scenario (``TripSettlementServiceTest``) the golden fixture was
    rendered from: one root throws, one root returns with three successful children."""
    failure = Threw(InvalidExpenseException("amount -12.00 EUR is not positive"))
    return TraceTree(
        [
            _call(
                "TripSettlementService",
                "recordExpense",
                ["tripName", "expense"],
                failure,
                [_call("ExpenseValidator", "ensureValid", ["expense"], failure)],
            ),
            _call(
                "TripSettlementService",
                "settleTrip",
                ["tripName"],
                Returned("SettlementPlan[transfers=0]"),
                [
                    _call("TripLedger", "expensesOf", ["tripName"], Returned("[]")),
                    _call("BalanceCalculator", "computeBalances", ["expenses"], Returned("{}")),
                    _call("SettlementPlanner", "planTransfers", ["balances"], Returned("[]")),
                ],
            ),
        ]
    )


class TestStructuralConformance:
    def test_renderer_reproduces_the_golden_artifact_byte_for_byte(self) -> None:
        golden = (_FIXTURES / "java-negative-expense.nt").read_bytes()

        rendered = (
            StructuralTraceRenderer()
            .render_document(
                _fair_split_negative_expense(),
                "Negative expense is rejected before touching the ledger",
            )
            .encode("utf-8")
        )

        assert rendered == golden
