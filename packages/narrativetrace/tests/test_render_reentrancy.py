# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the render-reentrancy defect (cross-port finding, Java's `RenderingGuard`).

Java's bug: `ValueRenderer` reflectively invoking a woven record accessor during
parameter/return capture ran that accessor's own instrumented bytecode, opening a real span for
a call the application never made — attributed as a root because rendering happens outside any
traced scope. Python has no bytecode weaving; tracing here is entirely `trace_object`'s proxy.
The equivalent hazard: a value being rendered exposes a hook that runs arbitrary application
code — `@narrative_summary`, or a stateless leaf's own `__str__`/`__repr__` (composite objects
never trust their own stringification, see `rendering.py`'s module docstring, so this is the
live surface) — and that hook calls a method on an object held as a field or closure that is
itself wrapped by `trace_object`. Calling that wrapped method through `__getattr__` genuinely
dispatches into `_TracedProxy`'s call wrapper, which (absent a guard) opens and closes a real
span for it.

Genuine accessor calls the traced method BODY itself makes must remain unaffected — the guard is
scoped to rendering, not a blanket suppression.
"""

from __future__ import annotations

import asyncio
import threading

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.markers import narrative_summary
from narrativetrace.rendering import is_rendering, rendering_scope
from narrativetrace.trace_object import trace_object


class Dependency:
    def compute(self) -> int:
        return 99


class Holder:
    """A parameter/return value whose ``@narrative_summary`` hook calls a traced dependency."""

    def __init__(self, dep: Dependency) -> None:
        self.dep = dep

    @narrative_summary
    def summary(self) -> str:
        return f"dep={self.dep.compute()}"


class ExplodingHolder:
    """Same hazard, but the summary hook raises after making the call."""

    def __init__(self, dep: Dependency) -> None:
        self.dep = dep

    @narrative_summary
    def summary(self) -> str:
        self.dep.compute()
        raise RuntimeError("boom during summary")


class HolderService:
    def receive(self, holder: Holder) -> None:
        return None

    def use(self, holder: Holder) -> int:
        # A genuine call the method BODY itself makes — must still be traced.
        return holder.dep.compute()

    def make(self, dep: Dependency) -> Holder:
        return Holder(dep)

    def receive_exploding(self, holder: ExplodingHolder) -> None:
        return None

    def add(self, a: int, b: int) -> int:
        return a + b


class TestParameterRenderingReentrancy:
    def test_rendering_a_traced_parameters_summary_produces_no_span_of_its_own(self) -> None:
        ctx = ContextVarNarrativeContext()
        dep = trace_object(Dependency(), ctx)
        svc = trace_object(HolderService(), ctx)

        svc.receive(Holder(dep))

        roots = ctx.capture_trace().roots
        assert [r.signature.method_name for r in roots] == ["receive"]
        assert roots[0].children == []

    def test_the_method_bodys_own_call_is_still_traced_as_a_child(self) -> None:
        ctx = ContextVarNarrativeContext()
        dep = trace_object(Dependency(), ctx)
        svc = trace_object(HolderService(), ctx)

        result = svc.use(Holder(dep))

        assert result == 99
        roots = ctx.capture_trace().roots
        assert [r.signature.method_name for r in roots] == ["use"]
        assert [c.signature.method_name for c in roots[0].children] == ["compute"]


class TestReturnValueRenderingReentrancy:
    def test_rendering_a_traced_returns_summary_produces_no_extra_span(self) -> None:
        ctx = ContextVarNarrativeContext()
        dep = trace_object(Dependency(), ctx)
        svc = trace_object(HolderService(), ctx)

        svc.make(dep)

        roots = ctx.capture_trace().roots
        assert [r.signature.method_name for r in roots] == ["make"]
        assert roots[0].children == []


class TestGuardClearedAfterAFailure:
    def test_a_raising_summary_during_rendering_leaves_the_guard_cleared_for_the_next_call(
        self,
    ) -> None:
        ctx = ContextVarNarrativeContext()
        dep = trace_object(Dependency(), ctx)
        svc = trace_object(HolderService(), ctx)

        svc.receive_exploding(ExplodingHolder(dep))
        assert svc.add(2, 3) == 5

        roots = ctx.capture_trace().roots
        assert [r.signature.method_name for r in roots] == ["receive_exploding", "add"]
        assert roots[0].children == []


class PausableHolder:
    """A ``@narrative_summary`` hook that blocks mid-render until released — lets a test pin a
    second thread's genuine call as running while the first is still inside rendering."""

    def __init__(
        self,
        dep: Dependency,
        entered_rendering: threading.Event,
        release_rendering: threading.Event,
    ) -> None:
        self.dep = dep
        self._entered_rendering = entered_rendering
        self._release_rendering = release_rendering

    @narrative_summary
    def summary(self) -> str:
        self._entered_rendering.set()
        self._release_rendering.wait(10)
        return f"dep={self.dep.compute()}"


class TestThreadIsolation:
    """Real OS thread preemption (unlike cooperative asyncio scheduling — see
    ``TestAsyncTaskIsolation``) can genuinely pause thread A mid-render while thread B makes a
    wholly unrelated, genuine traced call — the one scenario that would catch a naive *global*
    rendering flag shared across threads instead of a per-thread/task one."""

    def test_rendering_in_progress_on_one_thread_does_not_suppress_a_genuine_span_on_another(
        self,
    ) -> None:
        ctx = ContextVarNarrativeContext()
        entered_rendering = threading.Event()
        release_rendering = threading.Event()
        dep = trace_object(Dependency(), ctx)
        svc = trace_object(HolderService(), ctx)

        thread_a_trace: list[object] = []
        thread_a = self._start_thread_a(
            svc, dep, entered_rendering, release_rendering, thread_a_trace, ctx
        )
        assert entered_rendering.wait(10), "thread A must have entered rendering first"

        thread_b_result: list[int] = []
        thread_b_trace: list[object] = []
        thread_b = self._start_thread_b(svc, thread_b_result, thread_b_trace, ctx)
        thread_b.join(10)

        release_rendering.set()
        thread_a.join(10)

        self._assert_genuine_span_on_thread_b(thread_b_result, thread_b_trace)
        self._assert_rendering_suppressed_on_thread_a(thread_a_trace)

    @staticmethod
    def _start_thread_a(
        svc: HolderService,
        dep: Dependency,
        entered_rendering: threading.Event,
        release_rendering: threading.Event,
        trace_holder: list[object],
        ctx: ContextVarNarrativeContext,
    ) -> threading.Thread:
        def run() -> None:
            svc.receive(PausableHolder(dep, entered_rendering, release_rendering))  # type: ignore[arg-type]
            trace_holder.append(ctx.capture_trace())

        thread = threading.Thread(target=run)
        thread.start()
        return thread

    @staticmethod
    def _start_thread_b(
        svc: HolderService,
        result_holder: list[int],
        trace_holder: list[object],
        ctx: ContextVarNarrativeContext,
    ) -> threading.Thread:
        def run() -> None:
            result_holder.append(svc.add(2, 3))
            trace_holder.append(ctx.capture_trace())

        thread = threading.Thread(target=run)
        thread.start()
        return thread

    @staticmethod
    def _assert_genuine_span_on_thread_b(result: list[int], trace: list[object]) -> None:
        assert result == [5]
        roots = trace[0].roots  # type: ignore[attr-defined]
        assert [r.signature.method_name for r in roots] == ["add"]

    @staticmethod
    def _assert_rendering_suppressed_on_thread_a(trace: list[object]) -> None:
        roots = trace[0].roots  # type: ignore[attr-defined]
        assert [r.signature.method_name for r in roots] == ["receive"]
        assert roots[0].children == []


class TestAsyncTaskIsolation:
    """The full proxy pipeline renders synchronously (``@narrative_summary`` is a plain,
    non-``async`` hook — see ``_render_summary``), so a task performing it never yields
    control mid-render: under cooperative asyncio scheduling, a sibling task genuinely cannot
    interleave with it, which is exactly why the thread test above (real OS preemption) is the
    one that can catch a naive *global* guard. What asyncio *does* need proven is the isolation
    primitive itself — a :class:`contextvars.ContextVar` copies per task, so one task's "I am
    rendering" is invisible to a concurrently scheduled sibling even when that sibling runs
    while the first is (hypothetically) suspended mid-render. Exercised directly against the
    guard's own entry points, with a real ``await`` yield standing in for "suspended mid-render"
    — the one thing a synchronous integration test cannot construct on its own."""

    def test_the_rendering_flag_does_not_leak_into_a_concurrently_scheduled_sibling_task(
        self,
    ) -> None:
        observed: dict[str, bool] = {}

        async def rendering_task() -> None:
            with rendering_scope():
                await asyncio.sleep(0)  # yield control while "rendering" is still in progress
                observed["still_rendering_after_yield"] = is_rendering()

        async def sibling_task() -> None:
            await asyncio.sleep(0)
            observed["sibling_sees_rendering"] = is_rendering()

        async def run() -> None:
            await asyncio.gather(rendering_task(), sibling_task())

        asyncio.run(run())

        assert observed["still_rendering_after_yield"] is True
        assert observed["sibling_sees_rendering"] is False
