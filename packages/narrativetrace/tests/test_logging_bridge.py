# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the stdlib logging bridge (event consumer + context filter)."""

from __future__ import annotations

import logging

import pytest

from narrativetrace.events import (
    EnterEvent,
    ExitEvent,
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
)
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.logging_bridge import (
    _REQUEST_SCOPE,
    _SCOPE_STACK,
    EventType,
    LoggingTraceConsumer,
    NarrativeContextFilter,
    request_log_scope,
)
from narrativetrace.metadata import ServiceIdentity
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext

TRACE = TraceId("0" * 32)


def _span(
    hex_char: str, parent: SpanId | None = None, service: ServiceIdentity | None = None
) -> SpanContext:
    return SpanContext(
        trace_id=TRACE,
        span_id=SpanId(hex_char * 16),
        parent_span_id=parent,
        service_name=service.service_name if service else None,
        service_version=service.service_version if service else None,
        environment=service.environment if service else None,
    )


@pytest.fixture(autouse=True)
def _reset_scope() -> None:
    _SCOPE_STACK.set(None)
    _REQUEST_SCOPE.set(None)


class TestRequestLogScope:
    def test_request_scope_keys_stamped_on_records(
        self, captured: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("narrativetrace")
        filt = NarrativeContextFilter()
        logger.addFilter(filt)
        try:
            with request_log_scope({"traceId": "abc", "httpMethod": "GET"}):
                logger.info("in request")
            record = captured.records[-1]
            assert record.__dict__["traceId"] == "abc"
            assert record.__dict__["httpMethod"] == "GET"
        finally:
            logger.removeFilter(filt)

    def test_request_scope_cleared_on_exit(self) -> None:
        with request_log_scope({"traceId": "abc"}):
            assert _REQUEST_SCOPE.get() == {"traceId": "abc"}
        assert _REQUEST_SCOPE.get() is None

    def test_method_keys_override_request_scope(self, captured: pytest.LogCaptureFixture) -> None:
        consumer = LoggingTraceConsumer()
        logger = logging.getLogger("narrativetrace")
        filt = NarrativeContextFilter()
        logger.addFilter(filt)
        try:
            with request_log_scope({"httpMethod": "GET", "traceId": "req"}):
                consumer.accept(EnterEvent(_span("a"), 0, MethodSignature("Svc", "run", [])))
                logger.info("business")
            record = captured.records[-1]
            # request-only key survives; overlapping key is won by the method scope
            assert record.__dict__["httpMethod"] == "GET"
            assert record.__dict__["traceId"] == "0" * 32
            assert record.__dict__["nt.class"] == "Svc"
        finally:
            logger.removeFilter(filt)


@pytest.fixture
def captured(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger="narrativetrace")
    return caplog


class TestEventLogging:
    def test_enter_logged_at_debug_with_keys(self, captured: pytest.LogCaptureFixture) -> None:
        consumer = LoggingTraceConsumer()
        sig = MethodSignature("Svc", "run", [ParameterCapture("id", "7")])
        consumer.accept(EnterEvent(_span("a"), 0, sig))
        record = captured.records[-1]
        assert record.levelno == logging.DEBUG
        assert record.getMessage() == "→ Svc.run(id: 7)"
        assert record.__dict__["nt.class"] == "Svc"
        assert record.__dict__["nt.method"] == "run"
        assert record.__dict__["nt.depth"] == "1"
        assert record.__dict__["traceId"] == "0" * 32
        assert record.__dict__["traceName"] == "red fox runs"

    def test_redacted_param_in_enter_line(self, captured: pytest.LogCaptureFixture) -> None:
        consumer = LoggingTraceConsumer()
        sig = MethodSignature("S", "m", [ParameterCapture("pw", "", redacted=True)])
        consumer.accept(EnterEvent(_span("a"), 0, sig))
        assert captured.records[-1].getMessage() == "→ S.m(pw: [REDACTED])"

    def test_return_logged(self, captured: pytest.LogCaptureFixture) -> None:
        consumer = LoggingTraceConsumer()
        consumer.accept(ExitEvent(_span("a"), 10, Returned("42")))
        assert captured.records[-1].getMessage() == "← returned: 42"

    def test_exception_logged_at_warning_with_context(
        self, captured: pytest.LogCaptureFixture
    ) -> None:
        consumer = LoggingTraceConsumer()
        consumer.accept(ExitEvent(_span("a"), 10, Threw(ValueError("boom")), "failed to run"))
        record = captured.records[-1]
        assert record.levelno == logging.WARNING
        assert record.getMessage() == "!! ValueError: boom [failed to run]"

    def test_exception_message_sanitised(self, captured: pytest.LogCaptureFixture) -> None:
        consumer = LoggingTraceConsumer()
        consumer.accept(ExitEvent(_span("a"), 10, Threw(ValueError("a\nb"))))
        assert captured.records[-1].getMessage() == "!! ValueError: a\\nb"

    def test_service_identity_keys(self, captured: pytest.LogCaptureFixture) -> None:
        consumer = LoggingTraceConsumer()
        service = ServiceIdentity("orders", "1.2.3", "prod")
        consumer.accept(EnterEvent(_span("a", service=service), 0, MethodSignature("S", "m", [])))
        record = captured.records[-1]
        assert record.__dict__["service.name"] == "orders"
        assert record.__dict__["service.version"] == "1.2.3"
        assert record.__dict__["service.environment"] == "prod"

    def test_custom_level_map(self, captured: pytest.LogCaptureFixture) -> None:
        consumer = LoggingTraceConsumer(levels={EventType.EXCEPTION: logging.ERROR})
        consumer.accept(ExitEvent(_span("a"), 10, Threw(ValueError("x"))))
        assert captured.records[-1].levelno == logging.ERROR

    def test_concurrency_lifecycle_lines(self, captured: pytest.LogCaptureFixture) -> None:
        consumer = LoggingTraceConsumer()
        consumer.accept(ForkCreatedEvent("g1", 0))
        consumer.accept(MergeEvent("g1", 2, 0))
        consumer.accept(FireAndForgetEvent("g2", 0))
        messages = [r.getMessage() for r in captured.records[-3:]]
        assert messages == [
            "⑂ fork group created [groupId: g1]",
            "⑃ fork joined [groupId: g1, members: 2]",
            "⤳ fire-and-forget launched [groupId: g2]",
        ]


class TestDepthAndFilter:
    def test_depth_increments_and_root_exit_is_zero(
        self, captured: pytest.LogCaptureFixture
    ) -> None:
        consumer = LoggingTraceConsumer()
        parent = SpanId("a" * 16)
        consumer.accept(EnterEvent(_span("a"), 0, MethodSignature("S", "outer", [])))
        consumer.accept(EnterEvent(_span("b", parent=parent), 1, MethodSignature("S", "inner", [])))
        depths_in = [r.__dict__["nt.depth"] for r in captured.records[-2:]]
        assert depths_in == ["1", "2"]
        consumer.accept(ExitEvent(_span("b", parent=parent), 2, Returned("i")))
        consumer.accept(ExitEvent(_span("a"), 3, Returned("o")))
        assert captured.records[-1].__dict__["nt.depth"] == "0"

    def test_filter_stamps_keys_on_intervening_records(
        self, captured: pytest.LogCaptureFixture
    ) -> None:
        consumer = LoggingTraceConsumer()
        logger = logging.getLogger("narrativetrace")
        filt = NarrativeContextFilter()
        logger.addFilter(filt)
        try:
            consumer.accept(EnterEvent(_span("a"), 0, MethodSignature("Svc", "run", [])))
            logger.info("business log line")
            record = captured.records[-1]
            assert record.getMessage() == "business log line"
            assert record.__dict__["nt.class"] == "Svc"
            assert record.__dict__["traceId"] == "0" * 32
        finally:
            logger.removeFilter(filt)
