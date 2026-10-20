# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from billing.invoice_service import InvoiceService


def test_an_invoice_is_numbered_for_its_customer_and_amount():
    assert InvoiceService().issue_invoice("C-1", "tok_visa", 100) == "INV-C-1-100"
