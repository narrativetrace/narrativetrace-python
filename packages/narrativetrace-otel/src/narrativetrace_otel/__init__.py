# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""OpenTelemetry span bridge for narrativetrace traces.

Two entry points share the :mod:`narrativetrace_otel.attributes` mapper:

* :class:`~narrativetrace_otel.listener.OtelTraceEventListener` — live, span-per-event.
* :class:`~narrativetrace_otel.exporter.TraceSpanExporter` — batch, tree-to-spans.

With the OpenTelemetry SDK, build the provider with :func:`tracer_provider` and each span gets its
NarrativeTrace span id, so a late async child's parent is exact. The same effect without the helper
is ``TracerProvider(id_generator=NarrativeTraceIdGenerator())`` (from
:mod:`narrativetrace_otel.id_generator`) or ``OTEL_PYTHON_ID_GENERATOR=narrativetrace`` under
auto-instrumentation. Opt out with ``mirror_ids=False`` or ``NARRATIVETRACE_OTEL_MIRROR_IDS=false``.
"""

from narrativetrace_otel.exporter import TraceSpanExporter
from narrativetrace_otel.listener import OtelTraceEventListener
from narrativetrace_otel.provider import tracer_provider

__version__ = "0.5.0"

__all__ = [
    "OtelTraceEventListener",
    "TraceSpanExporter",
    "tracer_provider",
]
