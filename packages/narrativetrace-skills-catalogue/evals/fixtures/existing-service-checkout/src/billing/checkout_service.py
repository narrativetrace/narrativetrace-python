# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from shopkit import CheckoutFlow, Hooks

from billing.invoice_service import Invoice, InvoiceService
from billing.payment_gateway import PaymentGateway


class CheckoutService:
    """A checkout: issue the invoice, then take the payment through shopkit's flow."""

    def __init__(self, invoices: InvoiceService, gateway: PaymentGateway, hooks: Hooks) -> None:
        self._invoices = invoices
        self._flow = CheckoutFlow(gateway, hooks)

    def checkout(self, customer_id: str, amount_cents: int, card: str) -> Invoice:
        invoice = self._invoices.issue_invoice(customer_id, amount_cents)
        self._flow.run(invoice, card)
        return invoice
