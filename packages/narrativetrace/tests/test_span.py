# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the SpanContext correlation record."""

import dataclasses

import pytest

from narrativetrace.ids import SpanId, TraceId
from narrativetrace.metadata import HttpRoute
from narrativetrace.span import SpanContext

TRACE = TraceId("a" * 32)
SPAN = SpanId("b" * 16)


def test_minimal_span_has_required_ids_and_null_defaults() -> None:
    ctx = SpanContext(trace_id=TRACE, span_id=SPAN)
    assert ctx.trace_id is TRACE
    assert ctx.span_id is SPAN
    assert ctx.parent_span_id is None
    assert ctx.http_route is None
    assert ctx.story_id is None


def test_is_frozen() -> None:
    ctx = SpanContext(trace_id=TRACE, span_id=SPAN)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.span_name = "x"  # type: ignore[misc]


@pytest.mark.parametrize(("flags", "expected"), [(0, False), (1, True), (2, False), (3, True)])
def test_sampled_reads_bit_zero(flags: int, expected: bool) -> None:
    ctx = SpanContext(trace_id=TRACE, span_id=SPAN, trace_flags=flags)
    assert ctx.sampled is expected


def test_rejects_missing_trace_id() -> None:
    with pytest.raises(ValueError, match="traceId must not be None"):
        SpanContext(trace_id=None, span_id=SPAN)  # type: ignore[arg-type]


def test_rejects_missing_span_id() -> None:
    with pytest.raises(ValueError, match="spanId must not be None"):
        SpanContext(trace_id=TRACE, span_id=None)  # type: ignore[arg-type]


def test_carries_full_request_metadata() -> None:
    ctx = SpanContext(
        trace_id=TRACE,
        span_id=SPAN,
        http_method="POST",
        http_route=HttpRoute.of("/orders/{id}"),
        story_id="OrderService.placeOrder",
        chapter_id="OrderService.placeOrder",
    )
    assert ctx.http_method == "POST"
    assert str(ctx.http_route) == "/orders/{id}"
    assert ctx.chapter_id == ctx.story_id
