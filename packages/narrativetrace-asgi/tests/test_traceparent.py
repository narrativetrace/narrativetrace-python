# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins W3C traceparent parsing/formatting round-trips and rejection of malformed input."""

from __future__ import annotations

import pytest
from narrativetrace_asgi.traceparent import (
    format_traceparent,
    parse_traceparent,
)

from narrativetrace.ids import SpanId, TraceId

VALID = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"


class TestParse:
    def test_parses_valid_header(self) -> None:
        parsed = parse_traceparent(VALID)
        assert parsed is not None
        assert str(parsed.trace_id) == "0af7651916cd43dd8448eb211c80319c"
        assert str(parsed.span_id) == "b7ad6b7169203331"
        assert parsed.flags == 1
        assert parsed.sampled is True

    def test_unsampled_flag(self) -> None:
        parsed = parse_traceparent(VALID[:-2] + "00")
        assert parsed is not None
        assert parsed.sampled is False

    @pytest.mark.parametrize(
        "header",
        [
            None,
            "",
            "garbage",
            "00-tooShort-b7ad6b7169203331-01",
            "ff-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",  # forbidden version
            "00-" + "0" * 32 + "-b7ad6b7169203331-01",  # all-zero trace id
            "00-0af7651916cd43dd8448eb211c80319c-" + "0" * 16 + "-01",  # all-zero span id
            "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-0",  # bad flags length
            "00-0AF7651916CD43DD8448EB211C80319C-b7ad6b7169203331-01",  # uppercase
        ],
    )
    def test_rejects_malformed(self, header: str | None) -> None:
        assert parse_traceparent(header) is None


class TestRejectsWhatTheAbnfForbids:
    """Security fuzz suite Tier A finding: the hostile-corpus header cases surfaced two spec
    gaps neither of the two test classes above happened to cover -- the parser was more lenient
    than the W3C ABNF and Java's own implementation, which the shared corpus is built from."""

    VALID = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    def test_leading_whitespace_is_rejected_not_stripped(self) -> None:
        assert parse_traceparent(" " + self.VALID) is None

    def test_trailing_whitespace_is_rejected_not_stripped(self) -> None:
        assert parse_traceparent(self.VALID + " ") is None

    def test_version_00_rejects_a_trailing_delimiter(self) -> None:
        assert parse_traceparent(self.VALID + "-") is None

    def test_version_00_rejects_trailing_extension_fields(self) -> None:
        assert parse_traceparent(self.VALID + "-extra") is None

    def test_version_01_still_accepts_trailing_extension_fields(self) -> None:
        header = "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01-extra"
        assert parse_traceparent(header) is not None


class TestFormat:
    def test_round_trip(self) -> None:
        trace_id = TraceId("0af7651916cd43dd8448eb211c80319c")
        span_id = SpanId("b7ad6b7169203331")
        header = format_traceparent(trace_id, span_id)
        parsed = parse_traceparent(header)
        assert parsed is not None
        assert parsed.trace_id == trace_id
        assert parsed.span_id == span_id
        assert parsed.sampled is True

    def test_unsampled_format(self) -> None:
        header = format_traceparent(TraceId.generate(), SpanId.generate(), sampled=False)
        assert header.endswith("-00")
