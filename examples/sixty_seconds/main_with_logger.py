# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# main.py
import logging  # new: stdlib logging -- the sink this step sends the trace to
import sys  # new: stdout target for the handler below

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    NarrativeContextFilter,  # new: injects traceName/runName onto every log record
    TraceId,
    export_to_logger,  # new: replays an already-captured trace through your logger, one call
    trace_object,
)


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

# new: a plain stdlib logging setup -- the shape a real app's own logging config already has
handler = logging.StreamHandler(sys.stdout)
handler.addFilter(NarrativeContextFilter())  # new: makes traceName/runName available below
# new: DEBUG so export_to_logger's records pass the handler; the format reads the filter's keys
logging.basicConfig(
    level=logging.DEBUG, format="[%(traceName)s] [%(runName)s] %(message)s", handlers=[handler]
)

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

trace = context.capture_trace()  # new: capture once, reuse for both the print and the export
print(IndentedTextRenderer().render(trace))

export_to_logger(trace)  # new: sends the same captured trace through the configured logger
