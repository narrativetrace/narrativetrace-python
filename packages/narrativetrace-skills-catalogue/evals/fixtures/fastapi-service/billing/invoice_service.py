# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
class InvoiceService:
    """The service boundary: issues an invoice for a customer, charging a card token."""

    def issue_invoice(self, customer_id: str, card_token: str, amount_cents: int) -> str:
        return f"INV-{customer_id}-{amount_cents}"
