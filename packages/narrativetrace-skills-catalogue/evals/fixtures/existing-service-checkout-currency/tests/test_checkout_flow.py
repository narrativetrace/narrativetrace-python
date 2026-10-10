# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from billing.checkout_service import CheckoutService
from billing.customer_directory import CustomerDirectory
from billing.daily_rates import DailyRates
from billing.invoice_service import InvoiceService
from billing.payment_gateway import PaymentGateway
from billing.rate_table_converter import RateTableConverter

from narrativetrace import trace_object


def test_customer_checks_out(narrative_trace):
    gateway = PaymentGateway()
    checkout = trace_object(
        CheckoutService(
            trace_object(InvoiceService(), narrative_trace),
            trace_object(CustomerDirectory({"C-1001": "EUR"}), narrative_trace),
            trace_object(
                RateTableConverter(trace_object(DailyRates(), narrative_trace)), narrative_trace
            ),
            trace_object(gateway, narrative_trace),
        ),
        narrative_trace,
    )

    invoice = checkout.checkout("C-1001", 4599, "card-visa-4242")

    assert invoice.invoice_id == "INV-0001"
    assert gateway.captured == ["AUTH-card-visa-4242-4599-EUR"]
