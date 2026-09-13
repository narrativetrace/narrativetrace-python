# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`config-shape-logging-consumer-per-instance-depth`: `nt.depth` is a private counter on each
`LoggingTraceConsumer` instance, so two consumers replaying the same event stream each report
their own correct depth -- documentation/guides/logging.md
`#one-consumer-per-stream-many-handlers`.

Two fresh consumers each process the SAME single enter event. If `nt.depth` were a class-level
counter shared across instances (the pre-fix bug this claim replaces), the second consumer's
enter would observe a depth already bumped by the first (`2`, not `1`) -- so the two consumers'
observed depths would diverge even though both replay the identical event.
"""

from __future__ import annotations

import logging

from narrativetrace import ContextVarNarrativeContext, LoggingTraceConsumer, trace_object
from narrativetrace.pipeline.event_store import EventStore


class _Greeter:
    def greet(self) -> str:
        return "hello"


class _DepthCapture(logging.Handler):
    def __init__(self, sink: list[str | None]) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(getattr(record, "nt.depth", None))


def _capture_with(name: str) -> tuple[logging.Logger, logging.Handler, list[str | None]]:
    sink: list[str | None] = []
    logger = logging.getLogger(f"contract-probe.depth.{name}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = _DepthCapture(sink)
    logger.addHandler(handler)
    return logger, handler, sink


def observe() -> str:
    store = EventStore()
    context = ContextVarNarrativeContext(store=store)
    service = trace_object(_Greeter(), context)
    service.greet()
    enter_event = store.events()[0]

    logger_a, handler_a, sink_a = _capture_with("a")
    logger_b, handler_b, sink_b = _capture_with("b")
    try:
        LoggingTraceConsumer(logger_a).accept(enter_event)
        LoggingTraceConsumer(logger_b).accept(enter_event)
    finally:
        logger_a.removeHandler(handler_a)
        logger_b.removeHandler(handler_b)

    return "independent-depth" if sink_a == sink_b == ["1"] else "corrupted-depth"
