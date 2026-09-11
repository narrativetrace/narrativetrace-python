# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""ASGI middleware (Starlette/FastAPI) for narrativetrace request tracing.

* :class:`~narrativetrace_asgi.middleware.NarrativeTraceMiddleware` — per-request capture/export.
* :func:`~narrativetrace_asgi.accessor.get_narrative_context` — request-scoped context accessor
  (usable directly as a FastAPI ``Depends`` provider).
* :func:`~narrativetrace_asgi.outbound.attach_traceparent` — httpx outbound header injection.
* :mod:`~narrativetrace_asgi.traceparent` — W3C ``traceparent`` parse/format.
"""

from narrativetrace_asgi.accessor import get_narrative_context
from narrativetrace_asgi.middleware import (
    NarrativeTraceMiddleware,
    RequestContext,
    RequestExporter,
    RequestUserResolver,
    UserContext,
)
from narrativetrace_asgi.outbound import (
    attach_traceparent,
    attach_traceparent_async,
    traceparent_header,
)
from narrativetrace_asgi.traceparent import (
    Traceparent,
    format_traceparent,
    parse_traceparent,
)

__version__ = "0.1.1"

__all__ = [
    "NarrativeTraceMiddleware",
    "RequestContext",
    "RequestExporter",
    "RequestUserResolver",
    "Traceparent",
    "UserContext",
    "attach_traceparent",
    "attach_traceparent_async",
    "format_traceparent",
    "get_narrative_context",
    "parse_traceparent",
    "traceparent_header",
]
