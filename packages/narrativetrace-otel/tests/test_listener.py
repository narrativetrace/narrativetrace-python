# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the live OTel listener behaviours to Java's ``OtelTraceEventListener`` contract."""

from __future__ import annotations

from narrativetrace_otel import OtelTraceEventListener
from opentelemetry.trace import StatusCode
from otel_harness import Harness

from narrativetrace.canonical import SCHEMA_VERSION
from narrativetrace.events import EnterEvent, ExitEvent, FireAndForgetEvent, ForkCreatedEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.metadata import EnduserId, HttpRoute
from narrativetrace.outcomes import Incomplete, Returned, Threw
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext

T0 = 1_000_000


def _root_sc(**kw: object) -> SpanContext:
    return SpanContext(TraceId.generate(), SpanId.generate(), **kw)  # type: ignore[arg-type]


def _child_sc(parent: SpanContext) -> SpanContext:
    return SpanContext(parent.trace_id, SpanId.generate(), parent_span_id=parent.span_id)


def _enter(
    sc: SpanContext, cls: str, method: str, ts: int, params: list[ParameterCapture] | None = None
) -> EnterEvent:
    return EnterEvent(sc, ts, MethodSignature(cls, method, params or []))


def _emit(
    listener: OtelTraceEventListener, sc: SpanContext, cls: str, method: str, rendered: str | None
) -> None:
    listener(_enter(sc, cls, method, T0))
    listener(ExitEvent(sc, T0 + 1_000_000, Returned(rendered)))


class TestSpanLifecycle:
    def test_enter_and_exit_produces_one_span(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sc = _root_sc()
        listener(_enter(sc, "OrderService", "placeOrder", T0))
        listener(ExitEvent(sc, T0 + 5_000_000, Returned('"ok"')))

        assert len(otel.finished()) == 1
        assert otel.finished()[0].name == "OrderService.placeOrder"

    def test_span_start_and_end_anchored_to_event_timestamps(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sc = _root_sc()
        listener(_enter(sc, "Svc", "run", T0))
        listener(ExitEvent(sc, T0 + 5_000_000, Returned('"ok"')))

        span = otel.finished()[0]
        assert span.start_time == T0
        assert span.end_time == T0 + 5_000_000

    def test_span_has_class_and_method_attributes(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        _emit(listener, _root_sc(), "Svc", "run", '"ok"')

        attrs = otel.attrs(otel.finished()[0])
        assert attrs["narrative.class"] == "Svc"
        assert attrs["narrative.method"] == "run"

    def test_span_has_parameter_attributes_with_fallback_typing(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sig = [ParameterCapture("orderId", '"O-1"')]
        sc = _root_sc()
        listener(EnterEvent(sc, T0, MethodSignature("Svc", "process", sig)))
        listener(ExitEvent(sc, T0 + 1_000_000, Returned('"done"')))

        assert otel.attrs(otel.finished()[0])["narrative.param.orderId"] == "O-1"

    def test_span_has_outcome_attribute(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        _emit(listener, _root_sc(), "Svc", "calc", "42")

        assert otel.attrs(otel.finished()[0])["narrative.outcome"] == "42"

    def test_incomplete_outcome_is_tagged_in_flight(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sc = _root_sc()
        listener(_enter(sc, "Svc", "hang", T0))
        listener(ExitEvent(sc, T0 + 1_000_000, Incomplete()))

        assert otel.attrs(otel.finished()[0])["narrative.outcome"] == "in-flight"

    def test_exception_sets_error_status_and_records_event(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sc = _root_sc()
        listener(_enter(sc, "Svc", "fail", T0))
        listener(ExitEvent(sc, T0 + 1_000_000, Threw(RuntimeError("boom"))))

        span = otel.finished()[0]
        assert span.status.status_code == StatusCode.ERROR
        assert [e.name for e in span.events] == ["exception"]

    def test_void_return_emits_no_outcome_attribute(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        _emit(listener, _root_sc(), "Svc", "run", None)

        assert "narrative.outcome" not in otel.attrs(otel.finished()[0])


class TestParentChild:
    def test_nested_calls_produce_parent_child_spans(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        (parent,) = (_root_sc(),)
        child = _child_sc(parent)
        listener(_enter(parent, "OrderService", "placeOrder", T0))
        listener(_enter(child, "PaymentService", "charge", T0 + 100))
        listener(ExitEvent(child, T0 + 2_000_000, Returned('"paid"')))
        listener(ExitEvent(parent, T0 + 5_000_000, Returned('"ok"')))

        outer = otel.named("OrderService.placeOrder")
        inner = otel.named("PaymentService.charge")
        assert otel.parent_id(inner) == otel.span_id(outer)

    def test_root_span_has_no_parent(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        _emit(listener, _root_sc(), "Svc", "run", '"ok"')

        assert otel.finished()[0].parent is None

    def test_out_of_order_exits_resolve_by_span_id(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        parent = _root_sc()
        child = _child_sc(parent)
        listener(_enter(parent, "P", "run", T0))
        listener(_enter(child, "C", "work", T0 + 100))
        listener(ExitEvent(child, T0 + 1_000_000, Returned('"c"')))
        listener(ExitEvent(parent, T0 + 2_000_000, Returned('"p"')))

        assert {s.name for s in otel.finished()} == {"C.work", "P.run"}

    def test_parent_receives_child_completion_event(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        parent = _root_sc()
        child = _child_sc(parent)
        listener(_enter(parent, "Root", "handle", T0))
        listener(_enter(child, "Svc", "process", T0 + 100))
        listener(ExitEvent(child, T0 + 500, Returned('"ok"')))
        listener(ExitEvent(parent, T0 + 1000, Returned('"done"')))

        parent_span = otel.named("Root.handle")
        assert [e.name for e in parent_span.events] == ["Svc.process"]
        assert parent_span.events[0].timestamp == T0 + 500

    def test_root_exit_emits_no_event_on_parent(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        _emit(listener, _root_sc(), "Root", "handle", '"ok"')

        assert otel.finished()[0].events == ()

    def test_parent_already_evicted_does_not_crash(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        parent = _root_sc()
        child = _child_sc(parent)
        listener(_enter(parent, "Root", "handle", T0))
        listener(_enter(child, "Svc", "process", T0 + 100))
        listener(ExitEvent(parent, T0 + 200, Returned('"done"')))
        listener(ExitEvent(child, T0 + 500, Returned('"ok"')))

        assert len(otel.finished()) == 2


class TestTraceLevelAttributes:
    def test_root_has_trace_identity(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sc = _root_sc()
        _emit(listener, sc, "Svc", "run", '"ok"')

        attrs = otel.attrs(otel.finished()[0])
        assert attrs["narrative.trace_id"] == str(sc.trace_id)
        assert attrs["narrative.trace_name"] == sc.trace_id.human_name()

    def test_every_span_has_nt_schema_attributes(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        parent = _root_sc()
        child = _child_sc(parent)
        listener(_enter(parent, "P", "run", T0))
        listener(_enter(child, "C", "work", T0 + 100))
        listener(ExitEvent(child, T0 + 500, Returned('"c"')))
        listener(ExitEvent(parent, T0 + 1000, Returned('"p"')))

        for span in otel.finished():
            attrs = otel.attrs(span)
            assert attrs["nt.entryType"] == "entry"
            assert attrs["nt.schemaVersion"] == SCHEMA_VERSION

    def test_root_has_trace_level_attributes(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sc = _root_sc(
            service_name="order-svc",
            http_method="POST",
            http_route=HttpRoute.of("/api/orders"),
            enduser_id=EnduserId.of("user-42"),
        )
        _emit(listener, sc, "Svc", "handle", '"ok"')

        attrs = otel.attrs(otel.finished()[0])
        assert attrs["narrative.http.method"] == "POST"
        assert attrs["narrative.http.route"] == "/api/orders"
        assert attrs["narrative.enduser.id"] == "user-42"
        assert attrs["narrative.service.name"] == "order-svc"

    def test_child_span_has_no_trace_level_attributes(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        parent = _root_sc(service_name="svc", http_method="POST", enduser_id=EnduserId.of("u"))
        child = _child_sc(parent)
        listener(_enter(parent, "Svc", "handle", T0))
        listener(_enter(child, "Repo", "find", T0 + 100))
        listener(ExitEvent(child, T0 + 500_000, Returned('"ok"')))
        listener(ExitEvent(parent, T0 + 1_000_000, Returned('"done"')))

        child_attrs = otel.attrs(otel.named("Repo.find"))
        assert "narrative.http.method" not in child_attrs
        assert "narrative.enduser.id" not in child_attrs


class TestOrphansAndIgnored:
    def test_non_enter_exit_events_are_ignored(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        listener(ForkCreatedEvent("g1", T0))
        listener(FireAndForgetEvent("g2", T0 + 1))

        assert otel.finished() == []

    def test_exit_without_enter_creates_orphan_span(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sc = _root_sc()
        listener(ExitEvent(sc, T0, Returned('"x"')))

        span = otel.finished()[0]
        assert span.status.status_code == StatusCode.ERROR
        assert "enter event lost" in (span.status.description or "")

    def test_exit_without_enter_preserves_trace_level_attributes(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer)
        sc = _root_sc(
            service_name="order-svc",
            http_method="POST",
            http_route=HttpRoute.of("/api/orders"),
            enduser_id=EnduserId.of("user-42"),
        )
        listener(ExitEvent(sc, T0, Returned('"ok"')))

        attrs = otel.attrs(otel.finished()[0])
        assert attrs["narrative.service.name"] == "order-svc"
        assert attrs["narrative.http.method"] == "POST"
        assert attrs["narrative.enduser.id"] == "user-42"

    def test_orphan_evicted_by_capacity_has_orphaned_status(self, otel: Harness) -> None:
        listener = OtelTraceEventListener(otel.tracer, max_active_spans=1, ttl_seconds=3600)
        listener(_enter(_root_sc(), "Old", "stale", 1_000))
        listener(_enter(_root_sc(), "New", "fresh", 2_000))

        evicted = otel.finished()[0]
        assert evicted.name == "Old.stale"
        assert evicted.status.status_code == StatusCode.ERROR
        assert "orphan" in (evicted.status.description or "")

    def test_orphan_evicted_by_ttl(self, otel: Harness) -> None:
        clock = iter([0.0, 0.0, 100.0, 100.0, 100.0, 100.0])
        listener = OtelTraceEventListener(otel.tracer, ttl_seconds=1.0)
        # Inject a fast-forwarding clock into the underlying map.
        listener._active_spans._clock = lambda: next(clock)
        listener(_enter(_root_sc(), "Svc", "slow", 1_000_000))
        sc2 = _root_sc()
        listener(_enter(sc2, "Svc", "next", 2_000_000))
        listener(ExitEvent(sc2, 3_000_000, Returned('"ok"')))

        orphan = otel.named("Svc.slow")
        assert orphan.status.status_code == StatusCode.ERROR
