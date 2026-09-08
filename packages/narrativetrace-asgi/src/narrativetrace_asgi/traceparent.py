# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""W3C ``traceparent`` header parsing and formatting.

Java has no HTTP module that reads or writes trace headers (it always mints a fresh trace id per
request). This is a *TS-ahead* parity feature adopted here (http-di report §TS-HTTP-5 / outbound
injection note): inbound adoption threads a distributed trace id into the request context, and the
outbound formatter lets a service propagate its trace id server-to-server.

Format: ``{version}-{trace-id}-{parent-id}-{trace-flags}`` — version and flags are 2 hex chars,
trace-id 32, parent-id 16, all lowercase. Version ``ff`` and all-zero ids are invalid.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.ids import SpanId, TraceId

_VERSION = "00"
_INVALID_VERSION = "ff"
_ZERO_TRACE_ID = "0" * 32
_ZERO_SPAN_ID = "0" * 16
SAMPLED_FLAG = 0x01


@dataclass(frozen=True, slots=True)
class Traceparent:
    """A parsed W3C traceparent: the upstream trace id, parent span id, and flags."""

    trace_id: TraceId
    span_id: SpanId
    flags: int

    @property
    def sampled(self) -> bool:
        """Whether the sampled flag (bit 0) is set."""
        return (self.flags & SAMPLED_FLAG) != 0


def parse_traceparent(header: str | None) -> Traceparent | None:
    """Parses a ``traceparent`` header value, returning ``None`` when malformed or invalid.

    Whitespace is never tolerated (the ABNF has none in the value grammar; an HTTP layer that
    trims field-value OWS has already done so before this function sees the header) and version
    ``00`` must carry exactly four fields -- the ability to append future-version extension
    fields is granted explicitly to versions after it, not retroactively to the one already
    shipped.
    """
    if not header:
        return None
    parts = header.split("-")
    if len(parts) < 4:
        return None
    version, trace_hex, span_hex, flags_hex = parts[0], parts[1], parts[2], parts[3]
    if not _valid_version(version):
        return None
    if version == _VERSION and len(parts) != 4:
        return None
    if trace_hex == _ZERO_TRACE_ID or span_hex == _ZERO_SPAN_ID:
        return None
    flags = _parse_flags(flags_hex)
    if flags is None:
        return None
    try:
        return Traceparent(TraceId(trace_hex), SpanId(span_hex), flags)
    except ValueError:
        return None


def format_traceparent(trace_id: TraceId, span_id: SpanId, *, sampled: bool = True) -> str:
    """Builds a ``traceparent`` header value for an outbound request."""
    flags = SAMPLED_FLAG if sampled else 0
    return f"{_VERSION}-{trace_id}-{span_id}-{flags:02x}"


def _valid_version(version: str) -> bool:
    return len(version) == 2 and version != _INVALID_VERSION and _is_hex(version)


def _parse_flags(flags_hex: str) -> int | None:
    if len(flags_hex) != 2 or not _is_hex(flags_hex):
        return None
    return int(flags_hex, 16)


_HEX_DIGITS = frozenset("0123456789abcdef")


def _is_hex(text: str) -> bool:
    return len(text) > 0 and all(c in _HEX_DIGITS for c in text)
