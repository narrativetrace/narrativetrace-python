# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Normalizes request-derived context values before they reach a log or telemetry sink.

``ContextExport`` (adversarial-audit mirror, F6, 2026-09-02). A value here -- HTTP
method/route, client IP, end-user/session/tenant id -- comes off the wire, not out of application
code, so exporting it (never capturing it) gets the same defenses as any other attacker-reachable
text reaching a log line: control-stripped (CWE-117 log forging / line injection) and length-capped
(cardinality blowup, log flooding). This is an *export* concern, not a capture one: the raw value
stays in :class:`~narrativetrace.span.SpanContext` and in the JSON export, which already escapes
correctly on its own, and is normalised only where a sink's own rules apply -- the HTTP
middleware's log-scope keys and the OTel attribute mapper.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize

MAX_LENGTH = 256
"""Matches Java's ``ContextExport.MAX_LENGTH``."""


def export(value: str) -> str:
    """Control-strips and length-caps ``value`` for a log or telemetry sink.

    Escaping runs before capping so an escape sequence (e.g. ``\\n``) can never straddle the
    truncation boundary.
    """
    sanitized = control_sanitize(value)
    if len(sanitized) > MAX_LENGTH:
        return f"{sanitized[:MAX_LENGTH]}…"
    return sanitized
