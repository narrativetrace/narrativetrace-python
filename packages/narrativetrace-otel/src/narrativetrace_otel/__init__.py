# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""OpenTelemetry span bridge for narrativetrace traces.

Two entry points share the :mod:`narrativetrace_otel.attributes` mapper:

* :class:`~narrativetrace_otel.listener.OtelTraceEventListener` — live, span-per-event.
* :class:`~narrativetrace_otel.exporter.TraceSpanExporter` — batch, tree-to-spans.
"""

from narrativetrace_otel.exporter import TraceSpanExporter
from narrativetrace_otel.listener import OtelTraceEventListener

__version__ = "0.1.0"

__all__ = [
    "OtelTraceEventListener",
    "TraceSpanExporter",
]
