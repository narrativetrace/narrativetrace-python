# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-168: NarrativeTrace span ids mirrored into the SDK, and the listener's mode detection."""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
from narrativetrace_otel import OtelTraceEventListener, TraceSpanExporter, id_handoff
from narrativetrace_otel.id_generator import (
    MIRROR_IDS_ENV,
    RECENT_CAPACITY,
    NarrativeTraceIdGenerator,
    RecentIds,
    mirror_ids_enabled,
)
from narrativetrace_otel.id_handoff import IdSource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator
from otel_harness import Harness

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.events import EnterEvent, ExitEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

T0 = 1_000_000


class _FixedIds(IdGenerator):
    def generate_span_id(self) -> int:
        return 0xAAAAAAAAAAAAAAAA

    def generate_trace_id(self) -> int:
        return 0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB


def _harness(generator: IdGenerator) -> Iterator[Harness]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(id_generator=generator)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield Harness(provider.get_tracer("narrativetrace"), exporter)
    provider.shutdown()


@pytest.fixture
def mirrored() -> Iterator[Harness]:
    yield from _harness(NarrativeTraceIdGenerator(mirror=True))


def _sc(**kw: object) -> SpanContext:
    return SpanContext(TraceId.generate(), SpanId.generate(), **kw)  # type: ignore[arg-type]


def _run(listener: OtelTraceEventListener, sc: SpanContext, name: str = "run") -> None:
    sig = MethodSignature("Svc", name, [])
    listener(EnterEvent(sc, T0, sig))
    listener(ExitEvent(sc, T0 + 1000, Returned(None)))


def test_mirrored_spans_carry_their_narrativetrace_ids(mirrored: Harness) -> None:
    sc = _sc()
    _run(OtelTraceEventListener(mirrored.tracer), sc)

    span = mirrored.finished()[0]
    assert span.context is not None
    assert format(span.context.span_id, "016x") == sc.span_id.value
    assert format(span.context.trace_id, "032x") == sc.trace_id.value


def test_the_applications_own_spans_keep_the_delegates_ids() -> None:
    for harness in _harness(NarrativeTraceIdGenerator(_FixedIds(), mirror=True)):
        harness.tracer.start_span("own").end()
        span = harness.finished()[0]
        assert span.context is not None
        assert span.context.span_id == 0xAAAAAAAAAAAAAAAA
        assert span.context.trace_id == 0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB


def test_mirrored_ids_make_the_reconstructed_parent_exact_and_unmarked(mirrored: Harness) -> None:
    listener = OtelTraceEventListener(mirrored.tracer, max_active_spans=1)
    parent = _sc(trace_flags=1)
    _run(listener, parent, "parent")
    _run(listener, _sc(), "n1")
    _run(listener, _sc(), "n2")
    child = SpanContext(
        parent.trace_id, SpanId.generate(), parent_span_id=parent.span_id, trace_flags=1
    )
    info = ConcurrencyInfo("async-g", ConcurrencyKind.ASYNC)
    listener(EnterEvent(child, T0, MethodSignature("Worker", "child", []), info))
    listener(ExitEvent(child, T0 + 5, Returned(None)))

    span = mirrored.named("Worker.child")
    assert mirrored.parent_id(span) == mirrored.span_id(mirrored.named("Svc.parent"))
    assert "narrative.parent.synthetic" not in mirrored.attrs(span)
    assert span.parent is not None
    assert span.parent.is_remote is False


def test_without_the_generator_the_listener_takes_the_memory_path(otel: Harness) -> None:
    listener = OtelTraceEventListener(otel.tracer)
    sc = _sc()
    _run(listener, sc)

    span = otel.finished()[0]
    assert span.context is not None
    assert format(span.context.span_id, "016x") != sc.span_id.value


def test_an_offer_outside_start_span_is_never_taken() -> None:
    generator = NarrativeTraceIdGenerator(_FixedIds(), mirror=True)
    sc = _sc()
    offer = id_handoff.offer(sc, IdSource.LIVE)
    try:
        assert generator.generate_span_id() == int(sc.span_id.value, 16)
        assert generator.generate_span_id() == 0xAAAAAAAAAAAAAAAA  # taken once
    finally:
        id_handoff.withdraw(offer)
    assert generator.generate_span_id() == 0xAAAAAAAAAAAAAAAA
    assert id_handoff.current() is None


def test_nested_offers_restore_the_shadowed_one() -> None:
    outer = id_handoff.offer(_sc(), IdSource.LIVE)
    inner = id_handoff.offer(_sc(), IdSource.BATCH)
    assert id_handoff.current() is inner
    id_handoff.withdraw(inner)
    assert id_handoff.current() is outer
    id_handoff.withdraw(outer)
    assert id_handoff.current() is None


def test_live_and_batch_export_of_one_span_never_share_an_id_and_warn_once(
    mirrored: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    sc = _sc()
    sig = MethodSignature("Svc", "run", [])
    _run(OtelTraceEventListener(mirrored.tracer), sc)
    node = TraceNode(sig, [], Returned(None), T0, 1000, span_context=sc)

    with caplog.at_level(logging.WARNING, logger="narrativetrace_otel"):
        TraceSpanExporter(mirrored.tracer).export([node])
        TraceSpanExporter(mirrored.tracer).export([node])

    ids = {mirrored.span_id(s) for s in mirrored.finished()}
    assert len(ids) == 3, "three exports, three distinct OTel span ids"
    assert len([r for r in caplog.records if "NarrativeTrace:" in r.getMessage()]) == 1


def test_the_batch_exporter_alone_mirrors_ids(mirrored: Harness) -> None:
    sc = _sc()
    node = TraceNode(
        MethodSignature("Svc", "run", []), [], Returned(None), T0, 1000, span_context=sc
    )

    TraceSpanExporter(mirrored.tracer).export([node])

    assert mirrored.span_id(mirrored.finished()[0]) == int(sc.span_id.value, 16)


def test_recent_ids_forget_the_oldest_first() -> None:
    recent = RecentIds(2)
    assert recent.claim(1, IdSource.LIVE) is None
    assert recent.claim(2, IdSource.LIVE) is None
    assert recent.claim(1, IdSource.BATCH) is IdSource.LIVE
    assert recent.claim(3, IdSource.LIVE) is None  # evicts 1
    assert recent.claim(1, IdSource.BATCH) is None
    assert RECENT_CAPACITY == 4096


def test_the_opt_out_environment_variable_turns_mirroring_off() -> None:
    assert mirror_ids_enabled({}) is True
    assert mirror_ids_enabled({MIRROR_IDS_ENV: "true"}) is True
    assert mirror_ids_enabled({MIRROR_IDS_ENV: "false"}) is False
    assert mirror_ids_enabled({MIRROR_IDS_ENV: " FALSE "}) is False


def test_an_opted_out_generator_serves_every_span_from_the_delegate() -> None:
    for harness in _harness(NarrativeTraceIdGenerator(mirror=False)):
        sc = _sc()
        _run(OtelTraceEventListener(harness.tracer), sc)
        span = harness.finished()[0]
        assert span.context is not None
        assert format(span.context.span_id, "016x") != sc.span_id.value


def test_the_environment_opt_out_is_read_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MIRROR_IDS_ENV, "false")
    for harness in _harness(NarrativeTraceIdGenerator()):
        sc = _sc()
        _run(OtelTraceEventListener(harness.tracer), sc)
        span = harness.finished()[0]
        assert span.context is not None
        assert format(span.context.span_id, "016x") != sc.span_id.value


def test_the_entry_point_is_registered_for_otel_python_id_generator() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    points = tomllib.loads(pyproject.read_text())["project"]["entry-points"]
    assert points["opentelemetry_id_generator"] == {
        "narrativetrace": "narrativetrace_otel.id_generator:NarrativeTraceIdGenerator"
    }
