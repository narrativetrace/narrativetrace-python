# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-180: a fresh root mints the sampled trace flag, so a reconstructed parent is not unsampled.

Mirrors Java's ``SyntheticParentSamplingReproTest``: a late child past the listener's memory,
parented on a context reconstructed from the NarrativeTrace id, must survive the SDK's DEFAULT
sampler (``ParentBased(ALWAYS_ON)``, no sampler argument) in both id modes, exactly as the control
within the memory does. The events come from the real context, not hand-built flags.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from narrativetrace_otel import OtelTraceEventListener
from narrativetrace_otel.id_generator import NarrativeTraceIdGenerator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator
from otel_harness import Harness

from narrativetrace import ContextVarNarrativeContext, TraceEvent
from narrativetrace.pipeline.event_store import EventStore
from narrativetrace.signature import MethodSignature


class _ListeningStore(EventStore):
    def __init__(self, listener: OtelTraceEventListener) -> None:
        super().__init__()
        self._listener = listener

    def add(self, event: TraceEvent) -> None:
        self._listener(event)
        super().add(event)


def _harness(id_generator: IdGenerator | None) -> Iterator[Harness]:
    exporter = InMemorySpanExporter()
    # NO sampler argument: the SDK default, ParentBased(ALWAYS_ON).
    provider = (
        TracerProvider(id_generator=id_generator) if id_generator is not None else TracerProvider()
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield Harness(provider.get_tracer("narrativetrace"), exporter)
    provider.shutdown()


@pytest.fixture
def default_ids() -> Iterator[Harness]:
    yield from _harness(None)


@pytest.fixture
def mirrored() -> Iterator[Harness]:
    yield from _harness(NarrativeTraceIdGenerator(mirror=True))


def _parent_then_late_child(harness: Harness, max_active_spans: int) -> None:
    listener = OtelTraceEventListener(harness.tracer, max_active_spans=max_active_spans)
    context = ContextVarNarrativeContext(store=_ListeningStore(listener))
    parent = context.enter_method(MethodSignature("Service", "parent", []))
    continuation = context.snapshot()
    context.exit_method_with_return("1", parent)  # type: ignore[arg-type]
    other = context.enter_method(MethodSignature("Service", "other", []))
    context.exit_method_with_return("2", other)  # type: ignore[arg-type]
    with continuation.activate():
        child = context.enter_method(MethodSignature("Worker", "child", []))
        context.exit_method_with_return("3", child)  # type: ignore[arg-type]
    context.reset()


def _assert_child_exported_under_parent(harness: Harness) -> None:
    names = [s.name for s in harness.finished()]
    assert "Service.parent" in names, names
    assert "Worker.child" in names, f"late child dropped by the default sampler; exported: {names}"
    parent = harness.named("Service.parent")
    child = harness.named("Worker.child")
    attrs = harness.attrs(child)
    if "narrative.parent.synthetic" in attrs:
        # not mirrored, past the memory: the parent is the reconstructed NarrativeTrace id by design
        assert format(harness.parent_id(child), "016x") == attrs["narrative.parent_span_id"]
    else:
        assert harness.parent_id(child) == harness.span_id(parent)


def test_a_late_child_past_the_memory_is_exported_under_the_default_sampler(
    default_ids: Harness,
) -> None:
    _parent_then_late_child(default_ids, max_active_spans=1)
    _assert_child_exported_under_parent(default_ids)


def test_a_late_child_past_the_memory_is_exported_in_mirrored_mode(mirrored: Harness) -> None:
    _parent_then_late_child(mirrored, max_active_spans=1)
    _assert_child_exported_under_parent(mirrored)


def test_control_a_child_within_the_memory_is_exported(default_ids: Harness) -> None:
    _parent_then_late_child(default_ids, max_active_spans=8)
    _assert_child_exported_under_parent(default_ids)
