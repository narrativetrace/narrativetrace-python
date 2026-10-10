# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from billing.compose import compose
from billing.invoice_service import InvoiceService
from billing.ledger_service import LedgerService
from billing.notification_service import NotificationService
from billing.payment_gateway import PaymentGateway

from narrativetrace import trace_object


def test_customer_checks_out(narrative_trace):
    gateway = PaymentGateway()
    ledger = LedgerService()
    notifications = NotificationService()
    checkout = trace_object(
        compose(
            trace_object(InvoiceService(), narrative_trace),
            trace_object(gateway, narrative_trace),
            trace_object(ledger, narrative_trace),
            trace_object(notifications, narrative_trace),
        ),
        narrative_trace,
    )

    invoice = checkout.checkout("C-1001", 4599, "card-visa-4242")

    assert invoice.invoice_id == "INV-0001"
    assert gateway.captured == ["AUTH-card-visa-4242-4599"]
    assert ledger.entries == ["paid INV-0001"]
