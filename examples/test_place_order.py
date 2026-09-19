# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests behind README.md's "problem" section (`examples/place_order.py`): proves the "before"
and "after" methods really run, and that the only behavioral difference between them is the
deleted log lines -- both return the same value on success and let the same exception through on
failure."""

from __future__ import annotations

import logging

import pytest

from examples.place_order import (
    CatalogService,
    Collaborators,
    CustomerService,
    InventoryService,
    Order,
    OrderRepository,
    OrderRequest,
    OrderServiceAfter,
    OrderServiceBefore,
    PaymentService,
)


class _DecliningPaymentService(PaymentService):
    """A payment collaborator that always declines, to exercise the catch-log-rethrow branch."""

    def charge(self, amount: float) -> str:
        raise RuntimeError("payment declined")


def _collaborators(*, payments: PaymentService | None = None) -> Collaborators:
    return Collaborators(
        customers=CustomerService(),
        catalog=CatalogService(),
        inventory=InventoryService(),
        payments=payments or PaymentService(),
        orders=OrderRepository(),
    )


_REQUEST = OrderRequest(id="C-1234", sku="SKU-KB", qty=2)


def test_before_logs_entry_and_success_and_returns_the_saved_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = OrderServiceBefore(_collaborators())
    with caplog.at_level(logging.INFO):
        order = service.place_order(_REQUEST)

    assert order == Order(id="ORD-C-1234")
    templates = [record.msg for record in caplog.records]
    assert "Placing order %s" in templates
    assert "Order succeeded %s" in templates


def test_after_returns_the_same_order_with_zero_log_lines(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = OrderServiceAfter(_collaborators())
    with caplog.at_level(logging.DEBUG):
        order = service.place_order(_REQUEST)

    assert order == Order(id="ORD-C-1234")
    assert caplog.records == []


def test_before_logs_the_exception_and_still_reraises_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = OrderServiceBefore(_collaborators(payments=_DecliningPaymentService()))
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match="payment declined"):
        service.place_order(_REQUEST)

    failure = next(r for r in caplog.records if r.levelno == logging.ERROR)
    assert failure.msg == "Placing order failed %s"
    assert failure.exc_info is not None


def test_after_raises_the_same_exception_with_zero_log_lines(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = OrderServiceAfter(_collaborators(payments=_DecliningPaymentService()))
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError, match="payment declined"):
        service.place_order(_REQUEST)

    assert caplog.records == []
