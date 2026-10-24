# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""OpenTelemetry SDK id generator that gives a NarrativeTrace span its own span id.

``NarrativeTraceIdGenerator``. With mirrored ids, any parent NarrativeTrace names -- a parent
that finished long before its late async child started included -- is exactly the OpenTelemetry
span of that id, so :class:`~narrativetrace_otel.listener.OtelTraceEventListener` never has to
remember finished parents or reconstruct one. NarrativeTrace span ids are W3C 16-hex and trace ids
32-hex, the same formats OpenTelemetry uses.

Pattern: spans started by the listener and by
:class:`~narrativetrace_otel.exporter.TraceSpanExporter` get their NarrativeTrace span id (and,
when they have no parent, their NarrativeTrace trace id) through a
:class:`~contextvars.ContextVar` hand-off set around ``start_span``
(:mod:`narrativetrace_otel.id_handoff`). Every other span -- the application's own, an
instrumentation library's -- gets the delegate's ids, unchanged.

How to use: on by default wherever NarrativeTrace has a hook. The OpenTelemetry Python
auto-instrumentation loads an id generator from the ``opentelemetry_id_generator`` entry point
named by ``OTEL_PYTHON_ID_GENERATOR``; this package registers ``narrativetrace``, so
``OTEL_PYTHON_ID_GENERATOR=narrativetrace`` installs it. An application that builds its own
provider calls :func:`narrativetrace_otel.tracer_provider`, which installs it, or writes the one
line::

    TracerProvider(id_generator=NarrativeTraceIdGenerator())

Opt out with ``mirror_ids=False`` on the helper or ``NARRATIVETRACE_OTEL_MIRROR_IDS=false``: the
generator then hands every span the delegate's ids,
and the listener's runtime detection takes the memory + marked-synthetic path.

Edge case: an id is mirrored once. A second span offering an id already mirrored -- the same span
exported live by the listener and again from a captured tree by the exporter -- gets the
delegate's id instead, and when the two came from those two different paths a one-time warning
says the setup double-exports. The memory of mirrored ids is bounded
(:data:`RECENT_CAPACITY` ids), so a repeat further apart than that is not recognised.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from collections.abc import Mapping

from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator

from narrativetrace_otel import id_handoff
from narrativetrace_otel.id_handoff import IdOffer, IdSource

MIRROR_IDS_ENV = "NARRATIVETRACE_OTEL_MIRROR_IDS"
RECENT_CAPACITY = 4096

_LOG = logging.getLogger("narrativetrace_otel")


def mirror_ids_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Whether mirroring is on: everything but ``NARRATIVETRACE_OTEL_MIRROR_IDS=false``."""
    source = os.environ if environ is None else environ
    value = source.get(MIRROR_IDS_ENV)
    return value is None or value.strip().lower() != "false"


class RecentIds:
    """Bounded memory of the span ids a generator has mirrored, and by which path.

    The guard against two OpenTelemetry spans sharing one id. Bounded: the oldest id is forgotten
    first, so a repeat later than ``capacity`` mirrored spans is no longer recognised -- the price
    of a memory that cannot grow with traffic.
    """

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._sources: OrderedDict[int, IdSource] = OrderedDict()
        self._lock = threading.Lock()

    def claim(self, span_id: int, source: IdSource) -> IdSource | None:
        """Claims an id for one path: ``None`` when it was new (now claimed by ``source``),
        otherwise the path that claimed it first (the id must not be mirrored again)."""
        with self._lock:
            earlier = self._sources.get(span_id)
            if earlier is not None:
                return earlier
            self._sources[span_id] = source
            if len(self._sources) > self._capacity:
                self._sources.popitem(last=False)
            return None


class NarrativeTraceIdGenerator(IdGenerator):
    """Mirrors NarrativeTrace's span ids into the SDK; every other span gets the delegate's."""

    def __init__(self, delegate: IdGenerator | None = None, *, mirror: bool | None = None) -> None:
        """``delegate`` serves the application's own spans (default: the SDK's random ids);
        ``mirror=None`` reads the ``NARRATIVETRACE_OTEL_MIRROR_IDS`` opt-out."""
        self._delegate = delegate if delegate is not None else RandomIdGenerator()
        self._mirror = mirror_ids_enabled() if mirror is None else mirror
        self._recent = RecentIds(RECENT_CAPACITY)
        self._warn_lock = threading.Lock()
        self._double_export_warned = False

    @property
    def double_export_warned(self) -> bool:
        return self._double_export_warned

    def generate_span_id(self) -> int:
        offer = id_handoff.current()
        if offer is None or offer.span_id_taken or not self._mirror:
            return self._delegate.generate_span_id()
        offer.span_id_taken = True
        return offer.span_id if self._granted(offer) else self._delegate.generate_span_id()

    def generate_trace_id(self) -> int:
        offer = id_handoff.current()
        if offer is None or offer.trace_id_taken or not self._mirror:
            return self._delegate.generate_trace_id()
        offer.trace_id_taken = True
        return offer.trace_id if self._granted(offer) else self._delegate.generate_trace_id()

    def _granted(self, offer: IdOffer) -> bool:
        if offer.granted is None:
            if offer.span_id == 0 or offer.trace_id == 0:
                offer.granted = False
            else:
                earlier = self._recent.claim(offer.span_id, offer.source)
                offer.granted = earlier is None
                if earlier is not None and earlier is not offer.source:
                    self._warn_double_export()
        return offer.granted

    def _warn_double_export(self) -> None:
        with self._warn_lock:
            if self._double_export_warned:
                return
            self._double_export_warned = True
        _LOG.warning(
            "NarrativeTrace: the same span is exported both live (OtelTraceEventListener) and "
            "from a captured tree (TraceSpanExporter) into one OpenTelemetry SDK with mirrored "
            "ids; the repeat got a fresh id so no two spans share one, but the backend now shows "
            "the work twice. Use one of the two paths per span."
        )
