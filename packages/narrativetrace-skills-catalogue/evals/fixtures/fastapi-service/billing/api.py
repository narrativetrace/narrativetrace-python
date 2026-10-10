# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from fastapi import FastAPI

from billing.invoice_service import InvoiceService

app = FastAPI()
invoices = InvoiceService()


@app.get("/invoices/{customer_id}")
def issue_invoice(customer_id: str) -> dict[str, str]:
    return {"invoice": invoices.issue_invoice(customer_id, "tok_live_abc123", 4200)}
