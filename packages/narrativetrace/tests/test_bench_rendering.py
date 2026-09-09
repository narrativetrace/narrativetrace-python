# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Rendering-a-trace benchmarks (`poe bench` / `poe bench-gate`).

The Java `narrativetrace-benchmarks` module has no dedicated rendering benchmark of its own (its
JMH suite stops at proxy/context overhead) -- this is the starter coverage this port adds for a
path every one of this product's claims rests on just as heavily: turning a captured
`TraceTree` into the Markdown/indented-text/prose document a person or an AI agent actually
reads. The fixture tree is captured for real through `trace_object` + a live context (not
hand-built `TraceNode`s), so what gets timed is exactly the shape a caller's own capture would
produce: 1 root, 3 children, 9 grandchildren -- 13 nodes.
"""

from __future__ import annotations

from pytest_benchmark.fixture import BenchmarkFixture

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.trace_object import trace_object
from narrativetrace.tree import TraceTree


class _Leaf:
    def compute(self, value: int) -> int:
        return value * 2


class _Inner:
    def __init__(self, leaf: _Leaf) -> None:
        self._leaf = leaf

    def step(self, value: int) -> int:
        return sum(self._leaf.compute(value + i) for i in range(3))


class _Outer:
    def __init__(self, inner: _Inner) -> None:
        self._inner = inner

    def process(self, value: int) -> int:
        return sum(self._inner.step(value + i) for i in range(3))


def _captured_tree() -> TraceTree:
    """A real 13-node trace (1 root, 3 children, 9 grandchildren), captured through a live
    context rather than hand-built, so rendering is timed against a realistic shape."""
    context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.DETAIL))
    leaf = trace_object(_Leaf(), context)
    inner = trace_object(_Inner(leaf), context)
    outer = trace_object(_Outer(inner), context)
    outer.process(1)
    return context.capture_trace()


class TestRenderCapturedTrace:
    def test_markdown(self, benchmark: BenchmarkFixture) -> None:
        tree = _captured_tree()
        renderer = MarkdownRenderer()

        benchmark(lambda: renderer.render(tree))

    def test_indented(self, benchmark: BenchmarkFixture) -> None:
        tree = _captured_tree()
        renderer = IndentedTextRenderer()

        benchmark(lambda: renderer.render(tree))

    def test_prose(self, benchmark: BenchmarkFixture) -> None:
        tree = _captured_tree()
        renderer = ProseRenderer()

        benchmark(lambda: renderer.render(tree))
