# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Outbound W3C ``traceparent`` injection for server-to-server calls.

The middleware adopts an inbound ``traceparent``; this closes the loop by stamping the current
request's trace id onto outgoing ``httpx`` requests, so a NarrativeTrace trace id propagates
across services (the client half of http-di report §TS-HTTP-5). Java has no counterpart.

Usage::

    import httpx
    from narrativetrace_asgi import attach_traceparent

    client = httpx.AsyncClient(event_hooks={"request": [attach_traceparent]})

Both a sync and an async hook are provided so the same helper works with ``httpx.Client`` and
``httpx.AsyncClient``. ``httpx`` is an optional dependency and is never imported here.
"""

from __future__ import annotations

from typing import Any

from narrativetrace.ids import SpanId
from narrativetrace_asgi.accessor import get_narrative_context
from narrativetrace_asgi.traceparent import format_traceparent

_HEADER = "traceparent"


def traceparent_header() -> str | None:
    """Builds a ``traceparent`` value for the current request context, or ``None`` outside one."""
    context = get_narrative_context()
    if context is None:
        return None
    return format_traceparent(context.trace_id(), SpanId.generate())


def attach_traceparent(request: Any) -> None:
    """httpx sync request event-hook: injects the current ``traceparent`` if not already set."""
    _inject(request)


async def attach_traceparent_async(request: Any) -> None:
    """httpx async request event-hook: injects the current ``traceparent`` if not already set."""
    _inject(request)


def _inject(request: Any) -> None:
    if _HEADER in request.headers:
        return
    header = traceparent_header()
    if header is not None:
        request.headers[_HEADER] = header
