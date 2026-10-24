# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""0.5.1 parity: the render bound (B-185), the nesting guard (B-186), the gate class (B-187) and
the summary hook running once per capture -- the Python translation of Java's
``ValueRendererSharedSubgraphBudgetTest``, ``RenderingGuardNestingTest`` and
``RenderHookReachesProxiedCodeTest``.

A ladder of ``n`` rungs whose two fields hold the same next rung is ``n + 1`` objects reached by
``2**n`` paths: rendering once per path is exponential, so the rendered size must be bounded by
distinct objects and a total budget, never by paths.
"""

from __future__ import annotations

import threading
from typing import Any

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.markers import narrative_summary
from narrativetrace.rendering import ValueRenderer, is_rendering, rendering_scope
from narrativetrace.trace_object import trace_object
from narrativetrace.values import ListVal, ObjectVal, RenderedValue, StringVal

_RUNGS = 16
_MAX_CHARACTERS = 64 * 1024
_MAX_STRUCTURED_NODES = 4096
_MAX_NODES = 1024


class Rung:
    """Two fields, one referent: shared, never cyclic."""

    def __init__(self, nxt: object) -> None:
        self.left = nxt
        self.right = nxt


def _ladder(rungs: int) -> object:
    current: object = "leaf"
    for _ in range(rungs):
        current = Rung(current)
    return current


def _count_nodes(value: RenderedValue) -> int:
    if isinstance(value, ObjectVal):
        return 1 + sum(_count_nodes(v) for v in value.fields.values())
    if isinstance(value, ListVal):
        return 1 + sum(_count_nodes(v) for v in value.elements)
    return 1


def _count_strings(value: RenderedValue, text: str) -> int:
    if isinstance(value, ObjectVal):
        return sum(_count_strings(v, text) for v in value.fields.values())
    if isinstance(value, ListVal):
        return sum(_count_strings(v, text) for v in value.elements)
    return 1 if isinstance(value, StringVal) and value.value == text else 0


def _within_seconds(seconds: float, work: Any) -> Any:
    """Runs ``work`` on a daemon thread; fails (rather than hangs) when it outlives the timeout."""
    box: list[Any] = []
    thread = threading.Thread(target=lambda: box.append(work()), daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), f"did not finish within {seconds} seconds"
    return box[0]


def _distinct_tree(levels: int) -> object:
    if levels == 0:
        return "leaf"
    return [_distinct_tree(levels - 1) for _ in range(5)]


class TestSharedSubgraphBound:
    def test_a_shared_subgraph_ladder_renders_within_a_bounded_ceiling(self) -> None:
        rendered = _within_seconds(20, lambda: ValueRenderer().render(_ladder(_RUNGS)))

        assert len(rendered) < _MAX_CHARACTERS, f"{_RUNGS + 1} objects -> {len(rendered)} chars"

    def test_the_structured_path_bounds_the_same_ladder(self) -> None:
        structured = _within_seconds(20, lambda: ValueRenderer().render_structured(_ladder(_RUNGS)))

        assert _count_nodes(structured) < _MAX_STRUCTURED_NODES

    def test_a_depth_20_ladder_renders_in_linear_size_on_both_paths(self) -> None:
        ladder = _ladder(20)

        flat = _within_seconds(10, lambda: ValueRenderer().render(ladder))
        nodes = _count_nodes(_within_seconds(10, lambda: ValueRenderer().render_structured(ladder)))

        assert len(flat) < 4096
        assert nodes < 4 * 21

    def test_a_ladder_as_deep_as_the_depth_cap_renders_in_linear_size_on_both_paths(self) -> None:
        ladder = _ladder(ValueRenderer.MAX_DEPTH)

        flat = _within_seconds(10, lambda: ValueRenderer().render(ladder))
        nodes = _count_nodes(_within_seconds(10, lambda: ValueRenderer().render_structured(ladder)))

        assert len(flat) < 8192
        assert nodes < 4 * 33

    def test_a_repeated_instance_renders_as_a_back_reference_the_same_on_both_paths(self) -> None:
        ladder = _ladder(4)
        renderer = ValueRenderer()

        flat = renderer.render(ladder)
        structured = renderer.render_structured(ladder)

        assert "<repeat: Rung>" in flat
        assert flat.count("<repeat: Rung>") == _count_strings(structured, "<repeat: Rung>") > 0

    def test_a_small_shared_value_still_repeats_inline(self) -> None:
        shared = Rung("x")  # 3 values: below the repeat floor

        assert "<repeat" not in ValueRenderer().render([shared, shared])

    def test_an_unshared_graph_past_the_total_budget_ends_in_the_node_budget_marker(self) -> None:
        tree = _distinct_tree(6)
        renderer = ValueRenderer()

        flat = _within_seconds(10, lambda: renderer.render(tree))
        structured = _within_seconds(10, lambda: renderer.render_structured(tree))

        assert "<max-nodes>" in flat
        assert _count_strings(structured, "<max-nodes>") > 0
        assert _count_nodes(structured) < _MAX_NODES + 5 * ValueRenderer.MAX_DEPTH


class Counted:
    def __init__(self) -> None:
        self.calls = 0

    @narrative_summary
    def summary(self) -> str:
        self.calls += 1
        return "counted"


class TestSummaryHookRunsOncePerCapture:
    def test_a_summary_hook_runs_at_most_once_per_instance_per_capture(self) -> None:
        counted = Counted()

        text, _structured, _redacted = ValueRenderer().render_for_capture(
            [counted, counted, [counted]]
        )

        assert text == "[counted, counted, [counted]]"
        assert counted.calls == 1

    def test_the_return_path_shares_the_answer_between_the_two_renderings(self) -> None:
        counted = Counted()
        ctx = ContextVarNarrativeContext()

        class Service:
            def make(self) -> Counted:
                return counted

        trace_object(Service(), ctx).make()

        assert counted.calls == 1

    def test_a_failing_hook_is_not_repeated_either(self) -> None:
        class Failing:
            calls = 0

            @narrative_summary
            def summary(self) -> str:
                Failing.calls += 1
                raise RuntimeError("boom")

        item = Failing()
        ValueRenderer().render_for_capture([item, item])

        assert Failing.calls == 1


class _ReEntering:
    @narrative_summary
    def summary(self) -> str:
        ValueRenderer().render("a value rendered from inside the hook")
        return "re-entered"


class _GuardProbe:
    def __init__(self) -> None:
        self.called = False
        self.guard_active = False

    @narrative_summary
    def summary(self) -> str:
        self.called = True
        self.guard_active = is_rendering()
        return "probed"


class _Siblings:
    def __init__(self, first: object, second: object) -> None:
        self.first = first
        self.second = second


class TestGuardNests:
    def test_a_hook_that_re_enters_rendering_leaves_the_guard_up_for_the_rest_of_the_walk(
        self,
    ) -> None:
        probe = _GuardProbe()

        ValueRenderer().render(_Siblings(_ReEntering(), probe))

        assert probe.called
        assert probe.guard_active

    def test_an_inner_scope_restores_the_outer_guard_and_the_last_exit_clears_it(self) -> None:
        with rendering_scope():
            with rendering_scope():
                pass
            assert is_rendering()
        assert not is_rendering()


class _Dependency:
    def compute(self) -> int:
        return 99


class _CallsCollaborator:
    def __init__(self, dep: _Dependency) -> None:
        self.dep = dep

    @narrative_summary
    def summary(self) -> str:
        ValueRenderer().render("nested")  # the nested pair that used to drop the guard
        return f"dep={self.dep.compute()}"


class _Receiver:
    def receive(self, holder: _CallsCollaborator) -> None:
        return None

    def make(self, dep: _Dependency) -> _CallsCollaborator:
        return _CallsCollaborator(dep)


class TestHookReachesInterceptedCode:
    """Python has one interception engine (``trace_object``'s call wrapper); its gate reads the
    rendering guard before opening a span."""

    def test_a_summary_hook_calling_an_intercepted_collaborator_emits_no_span(self) -> None:
        ctx = ContextVarNarrativeContext()
        dep = trace_object(_Dependency(), ctx)
        svc = trace_object(_Receiver(), ctx)

        svc.receive(_CallsCollaborator(dep))
        svc.make(dep)

        roots = ctx.capture_trace().roots
        assert [r.signature.method_name for r in roots] == ["receive", "make"]
        assert all(r.children == [] for r in roots)
