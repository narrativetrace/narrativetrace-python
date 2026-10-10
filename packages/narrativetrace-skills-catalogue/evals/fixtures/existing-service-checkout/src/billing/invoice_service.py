# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from dataclasses import dataclass


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    customer_id: str
    amount_cents: int


class InvoiceService:
    """Issues invoices, numbered in order."""

    def __init__(self) -> None:
        self._issued = 0

    def issue_invoice(self, customer_id: str, amount_cents: int) -> Invoice:
        if amount_cents <= 0:
            raise ValueError("an invoice amount must be positive")
        self._issued += 1
        return Invoice(f"INV-{self._issued:04d}", customer_id, amount_cents)
