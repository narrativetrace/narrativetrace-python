# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# main.py
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceId, trace_object


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# snippet:begin fixedTraceId
# A fixed trace id, adopted so this page's embedded output always names the same trace. A real
# run generates a random one every time (never this -- it is this DEMO's own constant, not the
# library default) via the same TraceId.adopt_trace_id a servlet-style boundary uses for an
# inbound trace header.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")

# snippet:end fixedTraceId

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(IndentedTextRenderer().render(context.capture_trace()))
