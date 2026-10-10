# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from orders.order_service import InvoiceFormatter, OrderService


def test_an_order_is_numbered_from_its_customer_and_quantity() -> None:
    assert OrderService().proc("cust-1", 2) == "ORD-cust-1-2"


def test_keyword_callers_follow_a_rename() -> None:
    assert OrderService().proc(d="cust-7", x=3) == "ORD-cust-7-3"


def test_a_price_is_the_unit_price_times_the_quantity() -> None:
    assert OrderService().calc(250, 4) == 1000


def test_an_invoice_names_its_order() -> None:
    assert InvoiceFormatter().fmt("ORD-cust-1-2") == "Invoice for ORD-cust-1-2"
