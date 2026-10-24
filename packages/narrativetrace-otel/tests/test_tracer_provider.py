# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The tracer-provider helper: mirroring on by default for an application that adopts it."""

from __future__ import annotations

import logging

import pytest
from narrativetrace_otel import OtelTraceEventListener, tracer_provider
from narrativetrace_otel.id_generator import MIRROR_IDS_ENV, NarrativeTraceIdGenerator
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.id_generator import RandomIdGenerator

from narrativetrace.events import EnterEvent, ExitEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

T0 = 1_000_000


def _emit_one(provider: TracerProvider) -> tuple[SpanContext, int]:
    """Runs one NarrativeTrace span through the listener; returns it and the exported span id."""
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    sc = SpanContext(TraceId.generate(), SpanId.generate())
    listener = OtelTraceEventListener(provider.get_tracer("narrativetrace"))
    listener(EnterEvent(sc, T0, MethodSignature("Svc", "run", [])))
    listener(ExitEvent(sc, T0 + 1000, Returned(None)))
    context = exporter.get_finished_spans()[0].context
    assert context is not None
    return sc, context.span_id


def test_the_helpers_provider_mirrors_narrativetrace_span_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(MIRROR_IDS_ENV, raising=False)
    sc, exported = _emit_one(tracer_provider())
    assert format(exported, "016x") == sc.span_id.value


def test_other_provider_options_pass_through() -> None:
    provider = tracer_provider(shutdown_on_exit=False)
    assert isinstance(provider.id_generator, NarrativeTraceIdGenerator)


def test_the_option_opts_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MIRROR_IDS_ENV, raising=False)
    sc, exported = _emit_one(tracer_provider(mirror_ids=False))
    assert format(exported, "016x") != sc.span_id.value


def test_the_environment_opts_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MIRROR_IDS_ENV, "false")
    provider = tracer_provider()
    assert not isinstance(provider.id_generator, NarrativeTraceIdGenerator)


def test_a_callers_id_generator_is_kept_with_one_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(MIRROR_IDS_ENV, raising=False)
    mine = RandomIdGenerator()
    with caplog.at_level(logging.WARNING, logger="narrativetrace_otel"):
        provider = tracer_provider(id_generator=mine)
    assert provider.id_generator is mine
    assert len([r for r in caplog.records if r.name == "narrativetrace_otel"]) == 1


def test_a_callers_id_generator_under_opt_out_warns_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv(MIRROR_IDS_ENV, raising=False)
    with caplog.at_level(logging.WARNING, logger="narrativetrace_otel"):
        tracer_provider(id_generator=RandomIdGenerator(), mirror_ids=False)
    assert caplog.records == []


def test_set_global_registers_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: list[object] = []
    monkeypatch.setattr(trace, "set_tracer_provider", registered.append)
    provider = tracer_provider(set_global=True)
    assert registered == [provider]


def test_the_provider_is_not_registered_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: list[object] = []
    monkeypatch.setattr(trace, "set_tracer_provider", registered.append)
    tracer_provider()
    assert registered == []
