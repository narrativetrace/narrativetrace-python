# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Request-scoped accessor for the narrative context bound to the in-flight request.

The middleware binds the active :class:`~narrativetrace.context.NarrativeContext` into a
:class:`contextvars.ContextVar` for the duration of each request, so handlers, dependencies, and
traced services can retrieve *the same* context without threading it through call signatures.
Because it is contextvars-based, concurrent requests (threads or asyncio tasks) are isolated.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from narrativetrace.context import NarrativeContext

_CURRENT_CONTEXT: contextvars.ContextVar[NarrativeContext | None] = contextvars.ContextVar(
    "narrativetrace_asgi_context", default=None
)


def get_narrative_context() -> NarrativeContext | None:
    """Returns the context bound to the current request, or ``None`` outside a traced request."""
    return _CURRENT_CONTEXT.get()
