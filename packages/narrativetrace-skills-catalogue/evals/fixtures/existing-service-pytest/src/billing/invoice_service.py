# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one real service boundary this fixture owns. Nothing here knows about tracing."""


class InvoiceService:
    def issue_invoice(self, customer_id: str, card_token: str, amount: int) -> str:
        return f"INV-{customer_id}-{amount}"
