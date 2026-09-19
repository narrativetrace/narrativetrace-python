# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`config-shape-logger-threshold-does-not-shrink-capture`: raising your logger's level never
shrinks what `capture_trace()` returns -- the captured trace and the log line are two independent
readers of the same captured events -- documentation/faq.md `#two-dials-two-paths`.

`export_to_logger` is new at 0.1.2 -- it does not exist in the 0.1.1 wheel's public API at all, so
its import is deferred into `_replay_at_critical` rather than sitting at module level (same
reasoning as `export_to_logger_probe.py`): every probe module is imported by
`contract_probe.runner` regardless of whether its own entry is applicable at the installed
version. `ContextVarNarrativeContext`/`trace_object`/`Threw` exist at every version this contract
still checks, so those stay at module level.

The probe traces one call that raises, so the capture includes an exception exit -- the kind of
line the logger normally reports at WARNING. It then replays the SAME captured trace through a
logger pinned to CRITICAL (above WARNING, so even the exception line is suppressed) and asserts
two independent things: the replay produced zero log records (the logger threshold really did
silence everything), and the trace captured *before* that replay already had the full call
structure, including the exception outcome -- proving capture never consulted the logger's level
at all, in either direction.
"""

from __future__ import annotations

import logging

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.outcomes import Threw
from narrativetrace.trace_object import trace_object
from narrativetrace.tree import TraceTree


class _FlakyService:
    def place_order(self, customer_id: str) -> str:
        raise ValueError(f"declined for {customer_id}")


class _Collector(logging.Handler):
    def __init__(self, sink: list[logging.LogRecord]) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record)


def _capture_with_exception() -> TraceTree:
    context = ContextVarNarrativeContext()
    service = trace_object(_FlakyService(), context)
    try:
        service.place_order("cust-1")
    except ValueError:
        pass
    return context.capture_trace()


def _capture_is_complete(trace: TraceTree) -> bool:
    roots = trace.roots
    return (
        len(roots) == 1
        and roots[0].signature.method_name == "place_order"
        and isinstance(roots[0].outcome, Threw)
    )


def _replay_at_critical(trace: TraceTree) -> list[logging.LogRecord]:
    from narrativetrace.logging_bridge import export_to_logger

    records: list[logging.LogRecord] = []
    logger = logging.getLogger("contract-probe.logger-threshold")
    logger.setLevel(logging.CRITICAL)  # above WARNING: even the exception line is silenced
    logger.propagate = False
    handler = _Collector(records)
    logger.addHandler(handler)
    try:
        export_to_logger(trace, logger=logger)
    finally:
        logger.removeHandler(handler)
    return records


def observe() -> str:
    trace = _capture_with_exception()
    capture_complete = _capture_is_complete(trace)
    records = _replay_at_critical(trace)
    return "complete" if capture_complete and not records else "incomplete"
