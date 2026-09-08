# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Immutable span correlation record attached to enter and exit events.

``SpanContext``. This is the interoperability boundary between NarrativeTrace and
downstream systems (exporters, OpenTelemetry bridges): it packages span identity together with
service, request, and user fields known at capture time.

Values are captured when the span is created; changing request or user context later does not
retroactively mutate existing instances. The Java builder is replaced by keyword construction
plus :func:`dataclasses.replace` — the idiomatic Python equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.ids import SpanId, TraceId
from narrativetrace.metadata import ClientIp, EnduserId, HttpRoute, SessionId, TenantId


@dataclass(frozen=True, slots=True)
class SpanContext:
    """Span identity plus service/request/user fields, copied at creation time.

    ``host_name`` / ``process_pid`` / ``runtime_version`` are the canonical schema 1.2 process
    resource identity (``host.name``, ``process.pid``, ``process.runtime.version``). They are
    ``None`` unless a host supplies them: reading them is an environment probe, and the schema
    documents their absence as the default rather than an error.
    """

    trace_id: TraceId
    span_id: SpanId
    parent_span_id: SpanId | None = None
    trace_flags: int = 0
    trace_state: str | None = None
    service_name: str | None = None
    service_version: str | None = None
    environment: str | None = None
    http_method: str | None = None
    http_route: HttpRoute | None = None
    client_ip: ClientIp | None = None
    enduser_id: EnduserId | None = None
    session_id: SessionId | None = None
    tenant_id: TenantId | None = None
    span_name: str | None = None
    story_id: str | None = None
    chapter_id: str | None = None
    host_name: str | None = None
    process_pid: int | None = None
    runtime_version: str | None = None

    def __post_init__(self) -> None:
        if self.trace_id is None:
            raise ValueError("traceId must not be None")
        if self.span_id is None:
            raise ValueError("spanId must not be None")

    @property
    def sampled(self) -> bool:
        """Whether the W3C sampled flag (bit 0 of ``trace_flags``) is set."""
        return (self.trace_flags & 1) != 0
