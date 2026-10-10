# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from billing.invoice_service import InvoiceService


def test_invoices_are_numbered_in_order():
    service = InvoiceService()
    assert service.issue_invoice("C-1", 100).invoice_id == "INV-0001"
    assert service.issue_invoice("C-2", 200).invoice_id == "INV-0002"
