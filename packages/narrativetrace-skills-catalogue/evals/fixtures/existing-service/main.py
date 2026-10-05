# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# The project's entry point: it calls the service boundary and prints the result.
from billing.invoice_service import InvoiceService

service = InvoiceService()
print(service.issue_invoice("cust-1", "tok_live_abc123", 42))
