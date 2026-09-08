# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the per-event canonical entry form (``entry.schema.json``)."""

from __future__ import annotations

import json
import time

import pytest

import narrativetrace
from narrativetrace.canonical import (
    SCHEMA_VERSION,
    UNKNOWN_SERVICE,
    CanonicalEntry,
    MonotonicAnchor,
    ParameterEntry,
    entry_document,
    entry_from_event,
    entry_to_json,
)
from narrativetrace.events import (
    EnterEvent,
    ExitEvent,
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
    TraceEvent,
)
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext

TRACE = TraceId("0" * 32)
ANCHOR = MonotonicAnchor(epoch_millis=1_775_000_000_000, monotonic_nanos=5_000_000_000)


def _span(**kw: object) -> SpanContext:
    return SpanContext(trace_id=TRACE, span_id=SpanId("a" * 16), **kw)  # type: ignore[arg-type]


def _enter(sig: MethodSignature | None = None, **kw: object) -> EnterEvent:
    return EnterEvent(
        span_context=_span(**kw),
        timestamp_nanos=ANCHOR.monotonic_nanos,
        signature=sig if sig is not None else MethodSignature("OrderService", "place_order", []),
    )


def _enter_entry(service_name: str | None) -> CanonicalEntry:
    return entry_from_event(_enter(service_name=service_name), anchor=ANCHOR)


def _exit(outcome: TraceOutcome, **kw: object) -> ExitEvent:
    return ExitEvent(
        span_context=_span(**kw),
        timestamp_nanos=ANCHOR.monotonic_nanos,
        outcome=outcome,
    )


class TestEnterEvent:
    def test_maps_to_a_method_enter_entry(self) -> None:
        entry = entry_from_event(_enter(), anchor=ANCHOR)
        assert entry.nt_entry_type == "entry"
        assert entry.nt_event_type == "method_enter"
        assert entry.nt_schema_version == SCHEMA_VERSION
        assert entry.level == "trace"
        assert entry.code_namespace == "OrderService"
        assert entry.code_function == "place_order"

    def test_renders_the_call_as_the_message(self) -> None:
        sig = MethodSignature(
            "OrderService",
            "place_order",
            [ParameterCapture("id", '"42"'), ParameterCapture("card", "", redacted=True)],
        )
        entry = entry_from_event(_enter(sig), anchor=ANCHOR)
        assert entry.message == '→ OrderService.place_order(id: "42", card: [REDACTED])'

    def test_carries_parameters_with_redaction_applied(self) -> None:
        sig = MethodSignature(
            "Svc", "m", [ParameterCapture("id", '"42"'), ParameterCapture("pin", "", redacted=True)]
        )
        entry = entry_from_event(_enter(sig), anchor=ANCHOR)
        assert entry.nt_parameters == [
            ParameterEntry("id", '"42"', redacted=False),
            ParameterEntry("pin", "[REDACTED]", redacted=True),
        ]

    def test_omits_the_parameter_array_when_the_call_takes_none(self) -> None:
        entry = entry_from_event(_enter(), anchor=ANCHOR)
        assert entry.nt_parameters is None

    def test_carries_the_span_correlation_fields(self) -> None:
        event = _enter(
            None,
            service_name="order-service",
            environment="test",
            parent_span_id=SpanId("b" * 16),
            story_id="OrderService.place_order",
            chapter_id="OrderService.place_order#1",
        )
        entry = entry_from_event(event, anchor=ANCHOR)
        assert entry.service == "order-service"
        assert entry.environment == "test"
        assert entry.trace_id == "0" * 32
        assert entry.span_id == "a" * 16
        assert entry.parent_span_id == "b" * 16
        assert entry.nt_trace_name == "red fox runs"
        assert entry.nt_story_id == "OrderService.place_order"
        assert entry.nt_chapter_id == "OrderService.place_order#1"

    def test_leaves_the_parent_span_unset_for_a_root_call(self) -> None:
        entry = entry_from_event(_enter(), anchor=ANCHOR)
        assert entry.parent_span_id is None

    def test_carries_no_outcome_or_return_value(self) -> None:
        entry = entry_from_event(_enter(), anchor=ANCHOR)
        assert entry.nt_outcome is None
        assert entry.nt_return_value is None
        assert entry.exception_type is None


class TestExitEvent:
    def test_maps_a_return_to_a_successful_method_exit(self) -> None:
        event = _exit(Returned('"ok"'), span_name="OrderService.place_order")
        entry = entry_from_event(event, anchor=ANCHOR)
        assert entry.nt_event_type == "method_exit"
        assert entry.level == "trace"
        assert entry.nt_outcome == "success"
        assert entry.nt_return_value == '"ok"'
        assert entry.message == '← OrderService.place_order returned "ok"'

    def test_splits_the_span_name_into_namespace_and_function(self) -> None:
        event = _exit(Returned('"ok"'), span_name="OrderService.place_order")
        entry = entry_from_event(event, anchor=ANCHOR)
        assert entry.code_namespace == "OrderService"
        assert entry.code_function == "place_order"

    def test_treats_a_dotless_span_name_as_a_bare_function(self) -> None:
        entry = entry_from_event(_exit(Returned("1"), span_name="place_order"), anchor=ANCHOR)
        assert entry.code_namespace == ""
        assert entry.code_function == "place_order"

    def test_splits_a_dotted_span_name_at_the_first_dot(self) -> None:
        entry = entry_from_event(_exit(Returned("1"), span_name="a.b.c"), anchor=ANCHOR)
        assert entry.code_namespace == "a"
        assert entry.code_function == "b.c"

    def test_falls_back_to_empty_names_without_a_span_name(self) -> None:
        entry = entry_from_event(_exit(Returned("1")), anchor=ANCHOR)
        assert entry.code_namespace == ""
        assert entry.code_function == ""
        assert entry.message == "← method returned 1"

    def test_maps_a_void_return_without_a_value(self) -> None:
        event = _exit(Returned(None), span_name="Svc.m")
        entry = entry_from_event(event, anchor=ANCHOR)
        assert entry.nt_outcome == "success"
        assert entry.nt_return_value is None
        assert entry.message == "← Svc.m returned"

    def test_maps_a_throw_to_a_failed_method_exit(self) -> None:
        event = _exit(Threw(ValueError("card declined")), span_name="Svc.charge")
        entry = entry_from_event(event, anchor=ANCHOR)
        assert entry.level == "error"
        assert entry.nt_outcome == "failure"
        assert entry.exception_type == "ValueError"
        assert entry.exception_message == "card declined"
        assert entry.message == "!! ValueError: card declined"

    def test_maps_an_incomplete_exit(self) -> None:
        entry = entry_from_event(_exit(Incomplete(), span_name="Svc.m"), anchor=ANCHOR)
        assert entry.level == "trace"
        assert entry.nt_outcome == "incomplete"
        assert entry.message == "← Svc.m incomplete"


class TestConcurrencyEvents:
    @pytest.mark.parametrize(
        ("event", "event_type"),
        [
            (ForkCreatedEvent("g1", 5_000_000_000), "fork"),
            (MergeEvent("g1", 3, 5_000_000_000), "join"),
            (FireAndForgetEvent("g1", 5_000_000_000), "async_dispatch"),
        ],
    )
    def test_maps_each_group_marker_to_its_event_type(
        self, event: TraceEvent, event_type: str
    ) -> None:
        entry = entry_from_event(event, anchor=ANCHOR)
        assert entry.nt_event_type == event_type
        assert entry.nt_fork_id == "g1"
        assert entry.message == f"{event_type} [g1]"
        assert entry.level == "trace"
        assert entry.nt_entry_type == "entry"

    def test_group_markers_are_stamped_from_the_anchor(self) -> None:
        event = ForkCreatedEvent("g1", ANCHOR.monotonic_nanos + 1_000_000_000)
        entry = entry_from_event(event, anchor=ANCHOR)
        assert entry.timestamp == "2026-03-31T23:33:21.000Z"

    def test_group_markers_carry_no_span_correlation(self) -> None:
        entry = entry_from_event(ForkCreatedEvent("g1", 5_000_000_000), anchor=ANCHOR)
        # service is schema-required, so it carries the fallback rather than being absent.
        assert entry.service == UNKNOWN_SERVICE
        assert entry.trace_id is None
        assert entry.span_id is None
        assert entry.code_namespace is None
        assert entry.code_function is None
        assert entry.nt_outcome is None


class TestSerializer:
    def test_writes_the_dotted_schema_names(self) -> None:
        doc = json.loads(entry_to_json(entry_from_event(_enter(), anchor=ANCHOR)))
        assert doc["code.namespace"] == "OrderService"
        assert doc["code.function"] == "place_order"
        assert doc["nt.entryType"] == "entry"
        assert doc["nt.eventType"] == "method_enter"
        assert doc["nt.schemaVersion"] == SCHEMA_VERSION

    def test_writes_exception_fields_under_their_otel_names(self) -> None:
        event = _exit(Threw(ValueError("declined")), span_name="Svc.charge")
        doc = json.loads(entry_to_json(entry_from_event(event, anchor=ANCHOR)))
        assert doc["exception.type"] == "ValueError"
        assert doc["exception.message"] == "declined"

    def test_writes_parameters_as_an_array_of_objects(self) -> None:
        sig = MethodSignature(
            "Svc", "m", [ParameterCapture("id", '"42"'), ParameterCapture("pin", "", redacted=True)]
        )
        doc = json.loads(entry_to_json(entry_from_event(_enter(sig), anchor=ANCHOR)))
        assert doc["nt.parameters"] == [
            {"name": "id", "value": '"42"', "redacted": False},
            {"name": "pin", "value": "[REDACTED]", "redacted": True},
        ]

    def test_omits_every_unset_optional_field(self) -> None:
        doc = json.loads(entry_to_json(entry_from_event(_enter(), anchor=ANCHOR)))
        for absent in (
            "environment",
            "parent_span_id",
            "exception.type",
            "exception.message",
            "durationMs",
            "nt.outcome",
            "nt.forkId",
            "nt.branchIndex",
            "nt.causalId",
            "nt.returnValue",
            "nt.parameters",
            "nt.storyId",
            "nt.chapterId",
        ):
            assert absent not in doc

    def test_omits_span_fields_entirely_for_a_group_marker(self) -> None:
        doc = json.loads(entry_to_json(entry_from_event(ForkCreatedEvent("g1", 0), anchor=ANCHOR)))
        assert doc["nt.forkId"] == "g1"
        for absent in ("trace_id", "span_id", "code.namespace", "code.function"):
            assert absent not in doc
        # service is required by the schema; a marker still carries the fallback.
        assert doc["service"] == UNKNOWN_SERVICE

    def test_service_falls_back_when_the_host_pins_no_name(self) -> None:
        doc = json.loads(entry_to_json(_enter_entry(service_name=None)))
        assert doc["service"] == "unknown_service:python"

    def test_service_falls_back_when_the_host_pins_a_blank_name(self) -> None:
        doc = json.loads(entry_to_json(_enter_entry(service_name="   ")))
        assert doc["service"] == "unknown_service:python"

    def test_a_pinned_service_name_survives_the_fallback(self) -> None:
        doc = json.loads(entry_to_json(_enter_entry(service_name="order-service")))
        assert doc["service"] == "order-service"

    def test_service_is_never_the_literal_string_null(self) -> None:
        doc = json.loads(entry_to_json(_enter_entry(service_name=None)))
        assert doc["service"] != "null"

    def test_emits_fields_in_the_java_serializer_order(self) -> None:
        event = _exit(
            Threw(ValueError("boom")),
            span_name="Svc.m",
            service_name="svc",
            environment="test",
            parent_span_id=SpanId("b" * 16),
            story_id="s",
            chapter_id="c",
        )
        doc = json.loads(entry_to_json(entry_from_event(event, anchor=ANCHOR)))
        assert list(doc) == [
            "timestamp",
            "level",
            "message",
            "service",
            "environment",
            "trace_id",
            "span_id",
            "parent_span_id",
            "code.namespace",
            "code.function",
            "exception.type",
            "exception.message",
            "nt.entryType",
            "nt.eventType",
            "nt.schemaVersion",
            "nt.traceName",
            "nt.storyId",
            "nt.chapterId",
            "nt.outcome",
            "nt.exceptionPackage",
        ]

    def test_is_pretty_printed_with_two_space_indentation(self) -> None:
        raw = entry_to_json(entry_from_event(_enter(), anchor=ANCHOR))
        assert raw.startswith('{\n  "timestamp": ')
        assert '\n   "' not in raw
        assert raw.endswith("\n}")

    def test_emits_non_ascii_literally_rather_than_escaped(self) -> None:
        sig = MethodSignature("Pedido", "año", [])
        raw = entry_to_json(entry_from_event(_enter(sig), anchor=ANCHOR))
        assert "Pedido" in raw
        assert "año" in raw
        assert "\\u00f1" not in raw


class TestMonotonicAnchor:
    def test_maps_the_anchor_reading_to_its_wall_clock_moment(self) -> None:
        assert ANCHOR.timestamp(ANCHOR.monotonic_nanos) == "2026-03-31T23:33:20.000Z"

    def test_advances_wall_clock_by_the_monotonic_delta(self) -> None:
        assert (
            ANCHOR.timestamp(ANCHOR.monotonic_nanos + 1_500_000_000) == "2026-03-31T23:33:21.500Z"
        )

    def test_handles_readings_taken_before_the_anchor(self) -> None:
        assert (
            ANCHOR.timestamp(ANCHOR.monotonic_nanos - 1_000_000_000) == "2026-03-31T23:33:19.000Z"
        )

    def test_truncates_sub_millisecond_precision(self) -> None:
        assert ANCHOR.timestamp(ANCHOR.monotonic_nanos + 999_999) == "2026-03-31T23:33:20.000Z"

    def test_now_reads_both_clocks(self) -> None:
        before_millis, before_nanos = int(time.time() * 1000), time.perf_counter_ns()
        anchor = MonotonicAnchor.now()
        assert before_millis <= anchor.epoch_millis <= int(time.time() * 1000)
        assert before_nanos <= anchor.monotonic_nanos <= time.perf_counter_ns()

    @pytest.mark.parametrize(
        ("epoch_millis", "message"),
        [(-1, "epoch_millis must not be negative")],
    )
    def test_rejects_an_impossible_anchor(self, epoch_millis: int, message: str) -> None:
        with pytest.raises(ValueError, match=rf"\A{message}\Z"):
            MonotonicAnchor(epoch_millis=epoch_millis, monotonic_nanos=0)


class TestPublicSurface:
    def test_the_mapper_and_serialiser_are_reachable_from_the_distribution_root(self) -> None:
        anchor = narrativetrace.MonotonicAnchor.now()
        entry = narrativetrace.entry_from_event(_enter(), anchor=anchor)
        doc = json.loads(narrativetrace.entry_to_json(entry))
        assert doc["nt.entryType"] == "entry"
        for name in ("CanonicalEntry", "MonotonicAnchor", "entry_from_event", "entry_to_json"):
            assert name in narrativetrace.__all__


class TestUnknownEvent:
    def test_rejects_an_event_outside_the_sealed_union(self) -> None:
        class Rogue(TraceEvent):
            __slots__ = ()

        with pytest.raises(TypeError, match=r"\Aunknown TraceEvent type: Rogue\Z"):
            entry_from_event(Rogue(), anchor=ANCHOR)


class TestSerializerGuards:
    def test_the_document_form_rejects_a_missing_entry(self) -> None:
        with pytest.raises(ValueError, match=r"\Aentry must not be None\Z"):
            entry_document(None)  # type: ignore[arg-type]

    def test_the_json_form_rejects_a_missing_entry(self) -> None:
        with pytest.raises(ValueError, match=r"\Aentry must not be None\Z"):
            entry_to_json(None)  # type: ignore[arg-type]
