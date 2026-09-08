# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Building a module_of resolver from already-captured trace trees."""

from __future__ import annotations

from narrativetrace_glossary.class_package_index import class_package_index

from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree


def _node(
    class_name: str, package_name: str | None, children: list[TraceNode] | None = None
) -> TraceNode:
    return TraceNode(MethodSignature(class_name, "open", package_name=package_name), children or [])


def test_resolves_a_class_seen_under_exactly_one_module() -> None:
    tree = TraceTree([_node("OverdraftService", "acme.billing.overdraft")])

    module_of = class_package_index([tree])

    assert module_of("OverdraftService") == "acme.billing.overdraft"


def test_unseen_class_resolves_to_none() -> None:
    tree = TraceTree([_node("OverdraftService", "acme.billing.overdraft")])

    module_of = class_package_index([tree])

    assert module_of("SomethingElse") is None


def test_a_class_seen_under_two_distinct_modules_resolves_to_none() -> None:
    tree = TraceTree(
        [
            _node("Widget", "acme.billing.widget"),
            _node("Consumer", "acme.shipping", children=[_node("Widget", "acme.shipping.widget")]),
        ]
    )

    module_of = class_package_index([tree])

    assert module_of("Widget") is None


def test_a_class_seen_only_without_a_captured_module_resolves_to_none() -> None:
    tree = TraceTree([_node("Legacy", None)])

    module_of = class_package_index([tree])

    assert module_of("Legacy") is None


def test_resolves_across_nested_children_and_multiple_trees() -> None:
    child = _node("InventoryService", "acme.billing.inventory")
    first = TraceTree([_node("OrderService", "acme.billing.order", children=[child])])
    second = TraceTree([_node("PaymentService", "acme.billing.payment")])

    module_of = class_package_index([first, second])

    assert module_of("OrderService") == "acme.billing.order"
    assert module_of("InventoryService") == "acme.billing.inventory"
    assert module_of("PaymentService") == "acme.billing.payment"


def test_empty_trees_yield_a_resolver_that_answers_none_for_everything() -> None:
    module_of = class_package_index([])

    assert module_of("Anything") is None


def test_a_class_seen_twice_under_the_same_module_still_resolves() -> None:
    tree = TraceTree(
        [
            _node("Widget", "acme.billing.widget"),
            _node("Widget", "acme.billing.widget"),
        ]
    )

    module_of = class_package_index([tree])

    assert module_of("Widget") == "acme.billing.widget"
