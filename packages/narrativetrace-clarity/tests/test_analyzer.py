# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the analyzer: weighted overall, structural penalties, issue model, dedup, ranking."""

from __future__ import annotations

import pytest
from narrativetrace_clarity import Severity, analyze

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree


def _node(
    cls: str,
    method: str,
    params: list[str] | None = None,
    children: list[TraceNode] | None = None,
) -> TraceNode:
    captures = [ParameterCapture(p, "") for p in (params or [])]
    return TraceNode(MethodSignature(cls, method, captures), children or [], Returned(""))


def _tree(*roots: TraceNode) -> TraceTree:
    return TraceTree(list(roots))


class TestEnvelope:
    def test_empty_tree_envelope(self) -> None:
        result = analyze(_tree())
        assert result.method_name_score == 0.0
        assert result.class_name_score == 0.0
        assert result.parameter_name_score == 1.0
        assert result.structural_score == 1.0
        assert result.cohesion_score == pytest.approx(0.7)
        assert result.overall_score == pytest.approx(0.47)

    def test_overall_is_weighted_sum(self) -> None:
        result = analyze(_tree(_node("OrderService", "placeOrder", ["customerId"])))
        expected = (
            result.method_name_score * 0.30
            + result.class_name_score * 0.20
            + result.parameter_name_score * 0.25
            + result.structural_score * 0.15
            + result.cohesion_score * 0.10
        )
        assert result.overall_score == pytest.approx(expected)


class TestStructural:
    def test_four_params_no_penalty(self) -> None:
        node = _node("OrderService", "calculateTotal", ["a", "b", "c", "d"])
        assert analyze(_tree(node)).structural_score == pytest.approx(1.0)

    def test_five_params_penalty(self) -> None:
        node = _node("OrderService", "calculateTotal", ["a", "b", "c", "d", "e"])
        assert analyze(_tree(node)).structural_score == pytest.approx(0.9)

    def test_depth_five_no_penalty(self) -> None:
        node = _node("OrderService", "calculateTotal")
        for _ in range(4):
            node = _node("OrderService", "calculateTotal", children=[node])
        assert analyze(_tree(node)).structural_score == pytest.approx(1.0)

    def test_depth_six_penalty(self) -> None:
        node = _node("OrderService", "calculateTotal")
        for _ in range(5):
            node = _node("OrderService", "calculateTotal", children=[node])
        assert analyze(_tree(node)).structural_score == pytest.approx(0.95)


class TestIssues:
    def test_generic_method_flagged(self) -> None:
        result = analyze(_tree(_node("OrderService", "process")))
        method_issues = [i for i in result.issues if i.category == "method-name"]
        assert method_issues
        assert method_issues[0].element == "OrderService.process"

    def test_duplicate_param_deduped_with_summed_occurrences(self) -> None:
        tree = _tree(
            _node("A", "placeOrder", ["data"]),
            _node("B", "shipOrder", ["data"]),
        )
        result = analyze(tree)
        data_issues = [
            i for i in result.issues if i.category == "param-name" and i.element == "data"
        ]
        assert len(data_issues) == 1
        assert data_issues[0].occurrences == 2
        # "data" is a single VAGUE token → score 0.10 → HIGH(3); impact = 3 * 2 occurrences.
        assert data_issues[0].impact_score == pytest.approx(6.0)

    def test_issues_ranked_by_impact_descending(self) -> None:
        result = analyze(_tree(_node("Manager", "do", ["x", "data"])))
        impacts = [i.impact_score for i in result.issues]
        assert impacts == sorted(impacts, reverse=True)

    def test_collocation_issue_for_non_preferred_verb(self) -> None:
        result = analyze(_tree(_node("LedgerService", "checkLedger")))
        collocation = next(i for i in result.issues if i.category == "collocation")
        assert collocation.element == "LedgerService.checkLedger"
        assert "reconcileLedger" in collocation.suggestion
        assert collocation.severity is Severity.LOW

    def test_high_severity_for_very_poor_name(self) -> None:
        # "do" is GENERIC → single-token method score 0.10 (<= 0.20 → HIGH).
        result = analyze(_tree(_node("Widget", "do")))
        method_issue = next(i for i in result.issues if i.category == "method-name")
        assert method_issue.severity is Severity.HIGH


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): flattening and depth-scoring used unbounded native
    recursion with no depth bound or cycle guard -- both a cycle and a pathologically deep chain
    crashed with an uncaught RecursionError."""

    def test_a_self_referential_node_does_not_crash_analysis(self) -> None:
        node = _node("S", "run")
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        result = analyze(_tree(node))  # must not raise RecursionError
        assert result.structural_score <= 1.0

    def test_a_ten_thousand_deep_chain_does_not_overflow_the_stack(self) -> None:
        node = _node("S", "leaf")
        for _ in range(10_000):
            node = _node("S", "wrap", children=[node])
        result = analyze(_tree(node))  # must not raise RecursionError
        assert 0.0 <= result.structural_score <= 1.0
