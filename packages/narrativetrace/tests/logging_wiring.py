# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The default-logger row's wiring, as the framework table shows it: a stdlib handler carrying
``NarrativeContextFilter`` on the root logger, and the captured trace sent through it with
``export_to_logger``. Run as a script by ``test_logging_wiring.py``; ``llms-full.md`` carries the
``wiring`` region verbatim (``narrativetrace_tooling/frameworks/wiring-snippets.md``)."""

from __future__ import annotations

# snippet:begin wiring
import logging
import sys

from narrativetrace import (
    ContextVarNarrativeContext,
    NarrativeContextFilter,
    export_to_logger,
    trace_object,
)

handler = logging.StreamHandler(sys.stdout)
handler.addFilter(NarrativeContextFilter())
logging.basicConfig(level=logging.DEBUG, handlers=[handler])


def place_order_and_log(customer_id: str) -> None:
    context = ContextVarNarrativeContext()
    trace_object(OrderService(), context).place_order(customer_id)
    export_to_logger(context.capture_trace())
    # snippet:end wiring


class OrderService:
    def place_order(self, customer_id: str) -> str:
        return f"ORD-{customer_id}"


place_order_and_log("cust-1")
