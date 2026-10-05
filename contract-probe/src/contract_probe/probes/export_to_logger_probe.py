# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`config-shape-export-to-logger`: `export_to_logger(trace)` replays an already-captured
`TraceTree` through a private `LoggingTraceConsumer` in one call, with no `EventStore` to wire up
by hand -- documentation/sixty-seconds.md `#send-it-to-your-logger`.

The import is deferred into `observe()` rather than sitting at module level: `contract_probe.
runner` imports every probe module together, and this runner can be pointed at an OLDER published
artifact (`python -m scripts.contract_check <version>`), whose public API may not carry this
symbol at all -- a module-level import of it would then break every OTHER probe's import too, not
just this one's.
"""

from __future__ import annotations

import logging


class _OrderService:
    def place_order(self, customer_id: str) -> str:
        return f"ORD-{customer_id}"


class _Collector(logging.Handler):
    def __init__(self, sink: list[logging.LogRecord]) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record)


def observe() -> str:
    from narrativetrace import ContextVarNarrativeContext, export_to_logger, trace_object

    context = ContextVarNarrativeContext()
    service = trace_object(_OrderService(), context)
    service.place_order("cust-1")

    records: list[logging.LogRecord] = []
    logger = logging.getLogger("contract-probe.export-to-logger")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = _Collector(records)
    logger.addHandler(handler)
    try:
        export_to_logger(context.capture_trace(), logger=logger)
    finally:
        logger.removeHandler(handler)

    return "logged" if records else "not-logged"
