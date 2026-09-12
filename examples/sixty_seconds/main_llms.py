# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# main.py
from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    not_traced,
    trace_object,
)


class OrderService:
    @not_traced("customer_id")
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(IndentedTextRenderer().render(context.capture_trace()))
