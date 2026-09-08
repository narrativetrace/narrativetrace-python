# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the batch ``TraceSpanExporter`` to Java's nesting/duration/concurrency contract."""

from __future__ import annotations

from narrativetrace_otel import TraceSpanExporter
from opentelemetry.trace import StatusCode
from otel_harness import Harness

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.metadata import EnduserId, HttpRoute
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext
from narrativetrace.values import IntVal


def _node(
    cls: str,
    method: str,
    outcome: object = None,
    *,
    children: list[TraceNode] | None = None,
    params: list[ParameterCapture] | None = None,
    duration_nanos: int = 0,
    start_time_nanos: int = 0,
    concurrency: ConcurrencyInfo | None = None,
    span_context: SpanContext | None = None,
) -> TraceNode:
    return TraceNode(
        MethodSignature(cls, method, params or []),
        children or [],
        outcome,  # type: ignore[arg-type]
        duration_nanos,
        start_time_nanos,
        concurrency,
        span_context,
    )


def _sc(**kw: object) -> SpanContext:
    return SpanContext(TraceId.generate(), SpanId.generate(), **kw)  # type: ignore[arg-type]


class TestStructure:
    def test_one_span_per_node(self, otel: Harness) -> None:
        root = _node("A", "a", Returned("ok"), children=[_node("B", "b", Returned("ok"))])
        TraceSpanExporter(otel.tracer).export([root])
        assert len(otel.finished()) == 2

    def test_span_name_is_class_dot_method(self, otel: Harness) -> None:
        TraceSpanExporter(otel.tracer).export([_node("OrderService", "place", Returned("ok"))])
        assert otel.finished()[0].name == "OrderService.place"

    def test_child_span_nests_under_parent(self, otel: Harness) -> None:
        root = _node("A", "a", Returned("ok"), children=[_node("B", "b", Returned("ok"))])
        TraceSpanExporter(otel.tracer).export([root])
        parent = otel.named("A.a")
        child = otel.named("B.b")
        assert otel.parent_id(child) == otel.span_id(parent)

    def test_empty_list_produces_no_spans(self, otel: Harness) -> None:
        TraceSpanExporter(otel.tracer).export([])
        assert otel.finished() == []


class TestAttributes:
    def test_class_and_method_attributes(self, otel: Harness) -> None:
        TraceSpanExporter(otel.tracer).export([_node("Svc", "run", Returned("ok"))])
        attrs = otel.attrs(otel.finished()[0])
        assert attrs["narrative.class"] == "Svc"
        assert attrs["narrative.method"] == "run"

    def test_duration_ms_is_double(self, otel: Harness) -> None:
        node = _node("Svc", "run", Returned("ok"), duration_nanos=5_000_000)
        TraceSpanExporter(otel.tracer).export([node])
        assert otel.attrs(otel.finished()[0])["narrative.duration_ms"] == 5.0

    def test_returned_outcome_attribute(self, otel: Harness) -> None:
        TraceSpanExporter(otel.tracer).export([_node("Svc", "calc", Returned("42"))])
        assert otel.attrs(otel.finished()[0])["narrative.outcome"] == "42"

    def test_incomplete_outcome_in_flight(self, otel: Harness) -> None:
        TraceSpanExporter(otel.tracer).export([_node("Svc", "hang", Incomplete())])
        assert otel.attrs(otel.finished()[0])["narrative.outcome"] == "in-flight"

    def test_exception_node_error_status_and_event(self, otel: Harness) -> None:
        TraceSpanExporter(otel.tracer).export([_node("Svc", "fail", Threw(RuntimeError("boom")))])
        span = otel.finished()[0]
        assert span.status.status_code == StatusCode.ERROR
        assert [e.name for e in span.events] == ["exception"]

    def test_structured_param_flattens(self, otel: Harness) -> None:
        param = ParameterCapture("count", "5", False, IntVal(5))
        TraceSpanExporter(otel.tracer).export([_node("Svc", "run", Returned("ok"), params=[param])])
        assert otel.attrs(otel.finished()[0])["narrative.param.count"] == 5


class TestConcurrency:
    def test_sequential_node_has_no_concurrency_attributes(self, otel: Harness) -> None:
        TraceSpanExporter(otel.tracer).export([_node("Svc", "run", Returned("ok"))])
        attrs = otel.attrs(otel.finished()[0])
        assert "narrative.concurrency.groupId" not in attrs

    def test_concurrent_node_group_kind_thread(self, otel: Harness) -> None:
        info = ConcurrencyInfo("g-1", ConcurrencyKind.FORK_JOIN, thread_name="w", thread_id=42)
        TraceSpanExporter(otel.tracer).export(
            [_node("Svc", "run", Returned("ok"), concurrency=info)]
        )
        attrs = otel.attrs(otel.finished()[0])
        assert attrs["narrative.concurrency.groupId"] == "g-1"
        assert attrs["narrative.concurrency.kind"] == "FORK_JOIN"
        assert attrs["narrative.concurrency.threadId"] == 42

    def test_fire_and_forget_kind(self, otel: Harness) -> None:
        info = ConcurrencyInfo("g-2", ConcurrencyKind.FIRE_AND_FORGET)
        TraceSpanExporter(otel.tracer).export(
            [_node("Svc", "run", Returned("ok"), concurrency=info)]
        )
        assert otel.attrs(otel.finished()[0])["narrative.concurrency.kind"] == "FIRE_AND_FORGET"

    def test_task_label_emitted_when_present(self, otel: Harness) -> None:
        info = ConcurrencyInfo("g-3", ConcurrencyKind.FORK_JOIN, task_label="task-7")
        TraceSpanExporter(otel.tracer).export(
            [_node("Svc", "run", Returned("ok"), concurrency=info)]
        )
        assert otel.attrs(otel.finished()[0])["narrative.concurrency.taskLabel"] == "task-7"


class TestTraceLevel:
    def test_root_has_trace_level_attributes(self, otel: Harness) -> None:
        sc = _sc(
            service_name="svc",
            http_method="POST",
            http_route=HttpRoute.of("/o"),
            enduser_id=EnduserId.of("u"),
        )
        TraceSpanExporter(otel.tracer).export(
            [_node("Svc", "run", Returned("ok"), span_context=sc)]
        )
        attrs = otel.attrs(otel.finished()[0])
        assert attrs["narrative.http.method"] == "POST"
        assert attrs["narrative.enduser.id"] == "u"
        assert attrs["narrative.trace_id"] == str(sc.trace_id)

    def test_child_lacks_trace_level_attributes(self, otel: Harness) -> None:
        parent_sc = _sc(service_name="svc", http_method="POST", enduser_id=EnduserId.of("u"))
        child = _node("Repo", "find", Returned("ok"), span_context=_sc())
        root = _node("Svc", "run", Returned("ok"), children=[child], span_context=parent_sc)
        TraceSpanExporter(otel.tracer).export([root])
        assert "narrative.http.method" not in otel.attrs(otel.named("Repo.find"))


class TestChildEvents:
    def test_parent_has_event_per_direct_child(self, otel: Harness) -> None:
        children = [_node("A", "b", Returned("1")), _node("A", "c", Returned("2"))]
        TraceSpanExporter(otel.tracer).export(
            [_node("Root", "run", Returned("ok"), children=children)]
        )
        events = {e.name for e in otel.named("Root.run").events}
        assert events == {"A.b", "A.c"}

    def test_child_event_uses_child_completion_timestamp(self, otel: Harness) -> None:
        child = _node("Svc", "work", Returned("ok"), start_time_nanos=5000, duration_nanos=50_000)
        TraceSpanExporter(otel.tracer).export(
            [_node("Root", "run", Returned("ok"), children=[child])]
        )
        assert otel.named("Root.run").events[0].timestamp == 5000 + 50_000

    def test_root_without_children_has_no_events(self, otel: Harness) -> None:
        TraceSpanExporter(otel.tracer).export([_node("Root", "run", Returned("ok"))])
        assert otel.finished()[0].events == ()

    def test_grandchildren_do_not_event_on_grandparent(self, otel: Harness) -> None:
        grandchild = _node("Repo", "find", Returned("ok"))
        child = _node("Svc", "process", Returned("ok"), children=[grandchild])
        TraceSpanExporter(otel.tracer).export(
            [_node("Root", "run", Returned("ok"), children=[child])]
        )
        assert [e.name for e in otel.named("Root.run").events] == ["Svc.process"]


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): span export used unbounded native recursion with no
    depth bound or cycle guard -- both a cycle and a pathologically deep chain crashed with an
    uncaught RecursionError."""

    def test_a_self_referential_node_does_not_crash_export(self, otel: Harness) -> None:
        node = _node("S", "self", Returned("x"))
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        TraceSpanExporter(otel.tracer).export([node])  # must not raise RecursionError
        assert otel.attrs(otel.named("S.self"))["narrative.truncated"] == "cycle"

    def test_a_ten_thousand_deep_chain_is_truncated_not_crashed(self, otel: Harness) -> None:
        node = _node("S", "leaf", Returned("x"))
        for _ in range(10_000):
            node = _node("S", "wrap", Returned("x"), children=[node])
        TraceSpanExporter(otel.tracer).export([node])  # must not raise RecursionError
        assert len(otel.finished()) < 2000
        assert any(
            otel.attrs(span).get("narrative.truncated") == "depth-limit" for span in otel.finished()
        )
