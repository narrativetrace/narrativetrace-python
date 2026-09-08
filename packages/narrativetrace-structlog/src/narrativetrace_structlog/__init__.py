# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""structlog processor injecting narrativetrace correlation keys.

The SLF4J/MDC enrichment onto structlog. :func:`narrative_context_processor`
merges the *same* canonical keys as the stdlib :class:`~narrativetrace.NarrativeContextFilter`
(via :func:`narrativetrace.current_scope_keys`) into every structlog event dict, so the two
logging front-ends never drift — the cautionary tale being the TypeScript runtime's
enricher-vs-winston/pino key drift.

Usage::

    import structlog
    from narrativetrace_structlog import narrative_context_processor

    structlog.configure(
        processors=[narrative_context_processor, structlog.processors.JSONRenderer()]
    )
"""

from __future__ import annotations

from typing import Any

from narrativetrace import current_scope_keys

__version__ = "0.1.0"

__all__ = ["narrative_context_processor"]


def narrative_context_processor(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """A structlog processor adding the current scope's correlation keys (without overwriting)."""
    for key, value in current_scope_keys().items():
        event_dict.setdefault(key, value)
    return event_dict
