# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from billing.currency_converter import CurrencyConverter
from billing.customer_directory import CustomerDirectory
from billing.invoice_service import Invoice, InvoiceService
from billing.payment_gateway import PaymentGateway


class CheckoutService:
    """A checkout: the invoice in euro, the card charged in its own currency."""

    def __init__(
        self,
        invoices: InvoiceService,
        customers: CustomerDirectory,
        converter: CurrencyConverter,
        gateway: PaymentGateway,
    ) -> None:
        self._invoices = invoices
        self._customers = customers
        self._converter = converter
        self._gateway = gateway

    def checkout(self, customer_id: str, euro_cents: int, card: str) -> Invoice:
        invoice = self._invoices.issue_invoice(customer_id, euro_cents)
        currency = self._customers.card_currency(customer_id)
        charged = self._converter.convert(invoice.euro_cents, currency)
        authorization = self._gateway.authorize(charged, currency, card)
        self._gateway.confirm(authorization)
        return invoice
