# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Wires the checkout: the collaborators, and the side effects of a successful payment, each
registered on shopkit's checkout hooks."""

from shopkit import Hooks

from billing.checkout_service import CheckoutService
from billing.invoice_service import InvoiceService
from billing.ledger_service import LedgerService
from billing.notification_service import NotificationService
from billing.payment_gateway import PaymentGateway


def compose(
    invoices: InvoiceService,
    gateway: PaymentGateway,
    ledger: LedgerService,
    notifications: NotificationService,
) -> CheckoutService:
    hooks = Hooks()

    @hooks.on("payment_succeeded")
    def record_payment(invoice):
        ledger.record_paid(invoice.invoice_id)

    return CheckoutService(invoices, gateway, hooks)
