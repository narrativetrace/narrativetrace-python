# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for W3C trace/span identifier value types."""

import re

import pytest

from narrativetrace.ids import SpanId, TraceId


class TestTraceId:
    def test_accepts_32_lowercase_hex(self) -> None:
        value = "a" * 32
        assert TraceId(value).value == value

    def test_str_returns_raw_hex(self) -> None:
        value = "0123456789abcdef0123456789abcdef"
        assert str(TraceId(value)) == value

    @pytest.mark.parametrize(
        "bad",
        [
            "a" * 31,
            "a" * 33,
            "A" * 32,  # uppercase rejected
            "g" * 32,  # non-hex
            "",
        ],
    )
    def test_rejects_invalid(self, bad: str) -> None:
        with pytest.raises(ValueError, match="traceId must be 32 lowercase hex"):
            TraceId(bad)

    def test_generate_produces_valid_unique_ids(self) -> None:
        a, b = TraceId.generate(), TraceId.generate()
        assert re.fullmatch(r"[0-9a-f]{32}", a.value)
        assert a != b


class TestSpanId:
    def test_accepts_16_lowercase_hex(self) -> None:
        value = "0123456789abcdef"
        assert SpanId(value).value == value

    @pytest.mark.parametrize("bad", ["a" * 15, "a" * 17, "A" * 16, "z" * 16, ""])
    def test_rejects_invalid(self, bad: str) -> None:
        with pytest.raises(ValueError, match="spanId must be 16 lowercase hex"):
            SpanId(bad)

    def test_generate_produces_valid_hex(self) -> None:
        assert re.fullmatch(r"[0-9a-f]{16}", SpanId.generate().value)


def test_span_id_str_returns_raw_hex() -> None:
    value = "0123456789abcdef"
    assert str(SpanId(value)) == value
