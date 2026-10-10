# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The OpenTelemetry row's wiring, as the framework table shows it: ``OtelTraceEventListener``
attached to the context's event pipeline, so every traced call opens and closes a span as it runs.
Compiled and exercised by ``test_otel_wiring.py``; the doctor's ``config.otel-listener`` fix and
``llms-full.md`` carry the ``wiring`` region verbatim
(``narrativetrace_tooling/frameworks/wiring-snippets.md``)."""

from __future__ import annotations

# snippet:begin wiring
from narrativetrace_otel import OtelTraceEventListener
from opentelemetry import trace

from narrativetrace import ContextVarNarrativeContext, TraceEvent
from narrativetrace.pipeline.event_store import EventStore


class OtelEventStore(EventStore):
    """Hands every trace event to OpenTelemetry as it happens, and keeps it for capture_trace()."""

    def __init__(self, listener: OtelTraceEventListener) -> None:
        super().__init__()
        self._listener = listener

    def add(self, event: TraceEvent) -> None:
        self._listener(event)
        super().add(event)


context = ContextVarNarrativeContext(
    store=OtelEventStore(OtelTraceEventListener(trace.get_tracer("orders")))
)
# snippet:end wiring
