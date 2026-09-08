# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the e-commerce tour: every scenario runs, and each one shows what it claims to."""

from __future__ import annotations

import io
import json

import pytest

from examples.ecommerce.ecommerce import (
    ExternalServiceError,
    OutOfStockError,
    PaymentDeclinedError,
    UnknownCustomerError,
    capture_flaky_service,
    capture_out_of_stock,
    capture_payment_failure,
    capture_successful_order,
    capture_unknown_customer,
    capture_worker_thread_lookups,
    run_example,
    scenarios,
)
from examples.tour import Scenario
from narrativetrace import ContextVarNarrativeContext, Threw, TraceTree, export_json
from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.nodes import TraceNode


def _walk(nodes: list[TraceNode]) -> list[TraceNode]:
    out: list[TraceNode] = []
    for node in nodes:
        out.append(node)
        out.extend(_walk(node.children))
    return out


def _methods(tree: TraceTree) -> list[str]:
    return [f"{n.signature.class_name}.{n.signature.method_name}" for n in _walk(tree.roots)]


def _thrown(node: TraceNode) -> Threw:
    assert isinstance(node.outcome, Threw)
    return node.outcome


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: str(s.title))
def test_every_scenario_carries_a_wiring_note_and_runs(scenario: Scenario) -> None:
    assert scenario.wiring.startswith("Wiring: ")
    tree = scenario.run(ContextVarNarrativeContext())
    assert not tree.is_empty


def test_scenario_titles_follow_the_java_tour() -> None:
    assert [s.title for s in scenarios()] == [
        "Scenario 1: Successful Order + Async Notification",
        "Scenario 2: Payment Failure — Inventory Leak Bug",
        "Scenario 3: Flaky External Service",
        "Scenario 4: Unknown Customer",
        "Scenario 5: Out of Stock",
        "Scenario 6: Explicit Async Trace Capture",
    ]


def _fork_infos(tree: TraceTree) -> list[ConcurrencyInfo]:
    return [
        n.concurrency
        for n in _walk(tree.roots)
        if n.concurrency and n.concurrency.kind is ConcurrencyKind.FORK_JOIN
    ]


class TestSuccessfulOrder:
    def test_thread_pool_fork_children_share_one_group_id(self) -> None:
        """Discount + shipping: unchanged from before the asyncio notifier — real OS threads."""
        tree = capture_successful_order(ContextVarNarrativeContext())
        fork = [info for info in _fork_infos(tree) if info.thread_name is not None]
        assert len(fork) == 2  # calculate_discount + estimate
        assert len({info.group_id for info in fork}) == 1

    def test_asyncio_fork_children_share_a_different_group_id(self) -> None:
        """Email + loyalty: the second concurrency flavor — asyncio, not a thread pool worker."""
        tree = capture_successful_order(ContextVarNarrativeContext())
        fork = [info for info in _fork_infos(tree) if info.thread_name is None]
        assert len(fork) == 2  # send_confirmation + award_points
        assert len({info.group_id for info in fork}) == 1
        thread_pool_group = {info.group_id for info in _fork_infos(tree) if info.thread_name}
        assert {info.group_id for info in fork}.isdisjoint(thread_pool_group)

    def test_fire_and_forget_launcher_node_present(self) -> None:
        tree = capture_successful_order(ContextVarNarrativeContext())
        assert any(
            n.concurrency and n.concurrency.kind is ConcurrencyKind.FIRE_AND_FORGET
            for n in _walk(tree.roots)
        )

    def test_json_export_carries_concurrency_fields(self) -> None:
        text = json.dumps(
            json.loads(export_json(capture_successful_order(ContextVarNarrativeContext())))
        )
        assert "fork-" in text
        assert "fanf-" in text

    def test_card_token_is_redacted_and_the_order_is_narrated(self) -> None:
        tree = capture_successful_order(ContextVarNarrativeContext())
        charge = next(n for n in _walk(tree.roots) if n.signature.method_name == "charge")
        token = next(p for p in charge.signature.parameters if p.name == "card_token")
        assert token.redacted
        assert tree.roots[0].signature.narration == (
            "Placing order of 2 SKU-MECHANICAL-KB for customer C-1234"
        )


class TestAsyncNotification:
    """The demo-level twin of ``TestForkFromAsyncParent`` (core suite): a ForkJoinGroup created
    from inside an async traced method parents its children to it, not to the trace roots — the
    2026-09-08 core fix this scenario now proves in a printed trace, not just a unit test."""

    def test_email_and_loyalty_nest_under_the_async_notifier_not_as_roots(self) -> None:
        tree = capture_successful_order(ContextVarNarrativeContext())
        assert [r.signature.method_name for r in tree.roots] == ["place_order"]
        notifier = next(
            n for n in _walk(tree.roots) if n.signature.method_name == "notify_order_confirmed"
        )
        assert [c.signature.method_name for c in notifier.children] == [
            "send_confirmation",
            "award_points",
        ]
        assert all(
            c.concurrency is not None and c.concurrency.kind is ConcurrencyKind.FORK_JOIN
            for c in notifier.children
        )

    def test_async_notifier_carries_its_own_narration(self) -> None:
        tree = capture_successful_order(ContextVarNarrativeContext())
        notifier = next(
            n for n in _walk(tree.roots) if n.signature.method_name == "notify_order_confirmed"
        )
        assert notifier.signature.narration == (
            "Confirming order ORD-00001 to customer C-1234 by email and loyalty credit"
        )
        assert notifier.signature.class_name == "AsyncNotificationService"


class TestPaymentFailure:
    def test_reserve_is_called_but_release_never_is(self) -> None:
        tree = capture_payment_failure(ContextVarNarrativeContext())
        methods = _methods(tree)
        assert "InventoryService.reserve" in methods
        assert "InventoryService.release" not in methods

    def test_the_declined_charge_carries_its_error_context(self) -> None:
        tree = capture_payment_failure(ContextVarNarrativeContext())
        charge = next(n for n in _walk(tree.roots) if n.signature.method_name == "charge")
        assert isinstance(_thrown(charge).exception, PaymentDeclinedError)
        assert charge.signature.error_context == (
            "Payment declined for customer C-BROKE, amount was 79.96"
        )
        assert isinstance(_thrown(tree.roots[0]).exception, PaymentDeclinedError)


class TestFlakyService:
    def test_first_call_succeeds_and_the_second_fails(self) -> None:
        tree = capture_flaky_service(ContextVarNarrativeContext())
        first, second = tree.roots
        assert first.outcome is not None and not isinstance(first.outcome, Threw)
        assert isinstance(_thrown(second).exception, ExternalServiceError)
        assert second.signature.error_context == (
            "Failed to notify customer C-1234 about order ORD-00002"
        )


class TestFailureBranches:
    def test_unknown_customer_fails_at_the_lookup(self) -> None:
        tree = capture_unknown_customer(ContextVarNarrativeContext())
        assert _methods(tree) == ["OrderService.place_order", "CustomerService.find_customer"]
        lookup = tree.roots[0].children[0]
        assert isinstance(_thrown(lookup).exception, UnknownCustomerError)
        assert lookup.signature.error_context == "Customer C-UNKNOWN not found"

    def test_out_of_stock_fails_before_the_parallel_quotes(self) -> None:
        tree = capture_out_of_stock(ContextVarNarrativeContext())
        methods = _methods(tree)
        assert methods[-1] == "InventoryService.reserve"
        assert "DiscountService.calculate_discount" not in methods
        reserve = next(n for n in _walk(tree.roots) if n.signature.method_name == "reserve")
        assert isinstance(_thrown(reserve).exception, OutOfStockError)
        assert (
            reserve.signature.error_context == "Insufficient stock for SKU-USB-HUB, requested 9999"
        )


class TestExplicitAsyncCapture:
    def test_worker_thread_hands_back_only_its_own_lookups(self) -> None:
        tree = capture_worker_thread_lookups(ContextVarNarrativeContext())
        assert _methods(tree) == [
            "ProductCatalogService.lookup_price",
            "ProductCatalogService.lookup_price",
        ]
        assert [p.rendered_value for n in tree.roots for p in n.signature.parameters] == [
            '"SKU-MOUSE-PAD"',
            '"SKU-USB-HUB"',
        ]


def test_run_example_prints_every_scenario_header_in_order() -> None:
    out = io.StringIO()
    run_example(out)
    headers = [line for line in out.getvalue().splitlines() if line.startswith("=== ")]
    assert headers == [f"=== {s.title} ===" for s in scenarios()]
    assert "--- Markdown ---" in out.getvalue()
    assert "^ Notice: InventoryService.reserve was called" in out.getvalue()
