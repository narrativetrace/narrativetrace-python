# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Capture-overhead benchmarks (`poe bench` / `poe bench-gate`).

What one traced call costs, conceptually mirroring the Java `narrativetrace-benchmarks` module's
`ContextOverheadBenchmark` (the context's enter/exit/capture/reset cycle at each tracing level)
and `ProxyOverheadBenchmark` (a call through the tracing wrapper against the same call made
directly) — read for *what* to measure, not ported: this port has no JMH, no JDK proxies, and no
batching; every benchmark below is one self-contained operation, `reset()` included in its own
cost rather than hidden in an excluded fixture, matching Java's own documented reasoning for
doing the same.

No published numbers exist yet for this runtime (see `README.md`'s Performance section); this
file is the starter set that gives `poe bench-gate` something real to compare across runs.
"""

from __future__ import annotations

from pytest_benchmark.fixture import BenchmarkFixture

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.decorators import narrated, not_traced
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel
from narrativetrace.signature import MethodSignature
from narrativetrace.trace_object import trace_object

_SIGNATURE = MethodSignature("BenchService", "execute")


class _Plain:
    def execute(self, value: str) -> str:
        return f"result:{value}"


class _Narrated:
    @narrated("processed {value}")
    def execute(self, value: str) -> str:
        return f"result:{value}"


class _WithSecretParam:
    @not_traced("value")
    def execute(self, value: str) -> str:
        return f"result:{value}"


class TestContextEnterExitCaptureCycle:
    """One full cycle -- enter, exit, capture, reset -- at each tracing level."""

    def test_detail(self, benchmark: BenchmarkFixture) -> None:
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.DETAIL))

        def one_cycle() -> None:
            span_id = context.enter_method(_SIGNATURE)
            context.exit_method_with_return("result", span_id=span_id)
            context.capture_trace()
            context.reset()

        benchmark(one_cycle)

    def test_narrative(self, benchmark: BenchmarkFixture) -> None:
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.NARRATIVE))

        def one_cycle() -> None:
            span_id = context.enter_method(_SIGNATURE)
            context.exit_method_with_return("result", span_id=span_id)
            context.capture_trace()
            context.reset()

        benchmark(one_cycle)

    def test_off(self, benchmark: BenchmarkFixture) -> None:
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.OFF))

        def one_cycle() -> None:
            span_id = context.enter_method(_SIGNATURE)
            context.exit_method_with_return("result", span_id=span_id)
            context.capture_trace()
            context.reset()

        benchmark(one_cycle)


class TestTraceObjectCallOverhead:
    """A call through `trace_object` against the same call made directly, at DETAIL."""

    def test_direct_call_baseline(self, benchmark: BenchmarkFixture) -> None:
        target = _Plain()

        benchmark(lambda: target.execute("test"))

    def test_traced_call_no_narration(self, benchmark: BenchmarkFixture) -> None:
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.DETAIL))
        proxy = trace_object(_Plain(), context)

        def one_call() -> None:
            proxy.execute("test")
            context.reset()

        benchmark(one_call)

    def test_traced_call_narrated(self, benchmark: BenchmarkFixture) -> None:
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.DETAIL))
        proxy = trace_object(_Narrated(), context)

        def one_call() -> None:
            proxy.execute("test")
            context.reset()

        benchmark(one_call)

    def test_traced_call_redacted_param(self, benchmark: BenchmarkFixture) -> None:
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.DETAIL))
        proxy = trace_object(_WithSecretParam(), context)

        def one_call() -> None:
            proxy.execute("s3cr3t-value")
            context.reset()

        benchmark(one_call)

    def test_traced_call_off_context(self, benchmark: BenchmarkFixture) -> None:
        """The fast path: an OFF context short-circuits before any rendering work."""
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.OFF))
        proxy = trace_object(_Plain(), context)

        benchmark(lambda: proxy.execute("test"))
