# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The NarrativeTrace ids of the one span the calling context is about to start.

``IdOffer``. Offered to :class:`~narrativetrace_otel.id_generator.NarrativeTraceIdGenerator` for
the duration of a single ``start_span`` call.

Kept apart from the generator so the live listener and the batch exporter can offer ids without
importing any OpenTelemetry SDK module: an application with only the OpenTelemetry API installed
offers ids nobody takes, and nothing breaks.

Pattern: a :class:`~contextvars.ContextVar` hand-off, set right before ``start_span`` and reset
right after it (``try``/``finally`` at both call sites). The SDK generates a span's ids
synchronously on the starting thread, so the generator sees exactly this span's offer; each id is
taken at most once, so a span some span processor starts from inside ``start_span`` gets ordinary
ids.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from narrativetrace.span import SpanContext


class IdSource(Enum):
    """Which NarrativeTrace path started the span -- the two must never export one context twice."""

    LIVE = "live"
    BATCH = "batch"


@dataclass(eq=False)
class IdOffer:
    """One span's NarrativeTrace ids, on offer to the generator."""

    trace_id: int
    span_id: int
    source: IdSource
    token: contextvars.Token[IdOffer | None] | None = field(default=None, repr=False)
    span_id_taken: bool = False
    trace_id_taken: bool = False
    #: Whether this offer may be mirrored at all; decided once, at the first id the SDK asks for.
    granted: bool | None = None


_CURRENT: contextvars.ContextVar[IdOffer | None] = contextvars.ContextVar(
    "narrativetrace_otel_id_offer", default=None
)


def offer(span_context: SpanContext | None, source: IdSource) -> IdOffer | None:
    """Offers the ids of the span about to start in this context; pass the result to
    :func:`withdraw` in a ``finally``. A node without a span context offers nothing (``None``)."""
    if span_context is None:
        return None
    made = IdOffer(
        trace_id=int(span_context.trace_id.value, 16),
        span_id=int(span_context.span_id.value, 16),
        source=source,
    )
    made.token = _CURRENT.set(made)
    return made


def withdraw(made: IdOffer | None) -> None:
    """Withdraws an offer once its span has started, restoring any offer it shadowed."""
    if made is not None and made.token is not None:
        _CURRENT.reset(made.token)
        made.token = None


def current() -> IdOffer | None:
    """The calling context's open offer, or ``None``."""
    return _CURRENT.get()
