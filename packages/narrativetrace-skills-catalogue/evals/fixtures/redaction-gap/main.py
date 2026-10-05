# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# A deny-listed parameter name (payment_token) with no test proving redaction -- see README.md.
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, trace_object


class PaymentService:
    def charge(self, customer_id, payment_token, amount):
        return f"CHG-{customer_id}-{amount}"


context = ContextVarNarrativeContext()
service = trace_object(PaymentService(), context)
service.charge("C1", "tok_live_abc123", 42)
print(IndentedTextRenderer().render(context.capture_trace()))
