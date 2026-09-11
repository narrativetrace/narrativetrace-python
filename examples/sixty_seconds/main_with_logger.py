# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# main.py
import logging
import sys

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    LoggingTraceConsumer,
    trace_object,
)
from narrativetrace.pipeline.event_store import EventStore


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


logging.basicConfig(level=logging.DEBUG, format="%(message)s", stream=sys.stdout)

store = EventStore()
context = ContextVarNarrativeContext(store=store)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(IndentedTextRenderer().render(context.capture_trace()))

consumer = LoggingTraceConsumer()
for event in store.events():
    consumer.accept(event)
