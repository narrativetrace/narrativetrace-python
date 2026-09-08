# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the TraceNode read-model record."""

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature

SIG = MethodSignature("C", "m", [])


def test_defaults() -> None:
    node = TraceNode(SIG, [], Returned("x"))
    assert node.children == []
    assert node.duration_nanos == 0
    assert node.start_time_nanos == 0
    assert node.concurrency is None
    assert node.span_context is None


def test_duration_millis_truncates() -> None:
    node = TraceNode(SIG, [], Returned("x"), duration_nanos=1_999_999)
    assert node.duration_millis == 1


def test_synthetic_node_allows_none_outcome() -> None:
    assert TraceNode(SIG, [], None).outcome is None


def test_children_are_carried() -> None:
    child = TraceNode(MethodSignature("C", "child", []), [], Returned("y"))
    parent = TraceNode(SIG, [child], Returned("x"))
    assert parent.children[0] is child


def _chain(depth: int) -> TraceNode:
    node = TraceNode(SIG, [], Returned("x"))
    for _ in range(depth):
        node = TraceNode(SIG, [node], Returned("x"))
    return node


def _ring(length: int) -> TraceNode:
    """A ring of ``length`` nodes, each holding the next; ``length == 1`` holds itself.

    Each node gets a distinguishing method name by position: a ring of uniformly identical nodes
    is legitimately bisimilar to a same-content ring of a different length (their infinite
    unfoldings are indistinguishable), so a ring built for an *unequal* comparison needs content
    that actually varies by position, not just a different node count.
    """
    nodes = [TraceNode(MethodSignature("C", f"m{i}", []), [], Returned("x")) for i in range(length)]
    for i, node in enumerate(nodes):
        node.children.append(nodes[(i + 1) % length])
    return nodes[0]


def test_equal_deep_chains_compare_equal_without_a_stack_overflow() -> None:
    # Two independently built chains: dataclass equality can't shortcut on object identity.
    assert _chain(5_000) == _chain(5_000)


def test_unequal_deep_chains_compare_unequal_without_a_stack_overflow() -> None:
    left = _chain(5_000)
    right = TraceNode(MethodSignature("C", "different", []), left.children, Returned("x"))
    assert left != right


def test_equal_rings_compare_equal_without_a_stack_overflow() -> None:
    # Two independently built rings of the same shape: neither ring is identical-by-object-id,
    # so a naive structural walk revisits the same pair of nodes forever.
    assert _ring(2) == _ring(2)


def test_unequal_rings_compare_unequal_without_a_stack_overflow() -> None:
    left = _ring(3)
    right = _ring(3)
    right.children[0].children[0].children.clear()  # break the cycle: same length, differs
    assert left != right


def test_self_referential_node_equals_itself() -> None:
    node = TraceNode(SIG, [], Returned("x"))
    node.children.append(node)
    same = node
    assert node == same
