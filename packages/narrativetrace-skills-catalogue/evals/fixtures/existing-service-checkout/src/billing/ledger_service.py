# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
class LedgerService:
    """The accounting ledger."""

    def __init__(self) -> None:
        self.entries: list[str] = []

    def record_paid(self, invoice_id: str) -> None:
        self.entries.append(f"paid {invoice_id}")
