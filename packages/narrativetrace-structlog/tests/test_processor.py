# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the structlog processor to the same key set as the stdlib NarrativeContextFilter."""

from __future__ import annotations

import logging

import pytest
from narrativetrace_structlog import narrative_context_processor

from narrativetrace.events import EnterEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.logging_bridge import (
    _REQUEST_SCOPE,
    _SCOPE_STACK,
    LoggingTraceConsumer,
    NarrativeContextFilter,
    request_log_scope,
)
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext


@pytest.fixture(autouse=True)
def _reset_scope() -> None:
    _SCOPE_STACK.set(None)
    _REQUEST_SCOPE.set(None)


def _enter_span() -> None:
    span = SpanContext(TraceId("0" * 32), SpanId("a" * 16))
    LoggingTraceConsumer().accept(EnterEvent(span, 0, MethodSignature("OrderService", "place", [])))


class TestProcessor:
    def test_injects_span_keys(self) -> None:
        _enter_span()
        event = narrative_context_processor(None, "info", {"event": "hi"})
        assert event["traceId"] == "0" * 32
        assert event["nt.class"] == "OrderService"
        assert event["nt.method"] == "place"

    def test_injects_request_scope_keys(self) -> None:
        with request_log_scope({"httpMethod": "GET", "traceId": "req"}):
            event = narrative_context_processor(None, "info", {"event": "hi"})
        assert event["httpMethod"] == "GET"

    def test_does_not_overwrite_existing_event_keys(self) -> None:
        _enter_span()
        event = narrative_context_processor(None, "info", {"traceId": "preset"})
        assert event["traceId"] == "preset"

    def test_no_keys_outside_a_trace(self) -> None:
        assert narrative_context_processor(None, "info", {"event": "hi"}) == {"event": "hi"}

    def test_emits_identical_keys_to_stdlib_filter(self) -> None:
        """The structlog processor and the stdlib filter must produce the same key set."""
        _enter_span()
        with request_log_scope({"httpMethod": "GET"}):
            processor_keys = set(narrative_context_processor(None, "info", {})) - {"event"}

            record = logging.LogRecord("t", logging.INFO, __file__, 1, "m", None, None)
            NarrativeContextFilter().filter(record)
            base = set(logging.LogRecord("t", logging.INFO, __file__, 1, "m", None, None).__dict__)
            filter_keys = set(record.__dict__) - base

        assert processor_keys == filter_keys
