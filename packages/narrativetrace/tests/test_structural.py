# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Unit tests for :mod:`narrativetrace.render.structural` — the ``.nt`` grammar rules not already
pinned by the byte-for-byte golden conformance test (see ``test_structural_conformance.py``):
outcome-kind markers, concurrency grouping, walk limits, and identifier sanitization.
"""

from __future__ import annotations

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.structural import StructuralTraceRenderer
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree

_RENDERER = StructuralTraceRenderer()


def _node(
    class_name: str = "Service",
    method_name: str = "call",
    params: list[str] | None = None,
    outcome: TraceOutcome | None = None,
    children: list[TraceNode] | None = None,
    concurrency: ConcurrencyInfo | None = None,
) -> TraceNode:
    captures = [ParameterCapture(name, "value") for name in (params or [])]
    return TraceNode(
        signature=MethodSignature(class_name, method_name, captures),
        children=children or [],
        outcome=outcome,
        concurrency=concurrency,
    )


class TestOutcomeKinds:
    def test_void_return_renders_no_arrow(self) -> None:
        tree = TraceTree([_node(outcome=Returned(None))])
        assert _RENDERER.render(tree) == "- Service.call()\n"

    def test_non_void_return_renders_literal_value(self) -> None:
        tree = TraceTree([_node(outcome=Returned("42"))])
        assert _RENDERER.render(tree) == "- Service.call() → value\n"

    def test_thrown_exception_renders_simple_type_name_never_the_message(self) -> None:
        tree = TraceTree([_node(outcome=Threw(ValueError("super secret message")))])
        rendered = _RENDERER.render(tree)
        assert rendered == "- Service.call() !! ValueError\n"
        assert "secret" not in rendered

    def test_incomplete_renders_marker(self) -> None:
        tree = TraceTree([_node(outcome=Incomplete())])
        assert _RENDERER.render(tree) == "- Service.call() ?? incomplete\n"

    def test_no_outcome_renders_nothing_extra(self) -> None:
        tree = TraceTree([_node(outcome=None)])
        assert _RENDERER.render(tree) == "- Service.call()\n"


class TestNamesOnly:
    def test_parameter_names_appear_values_never_do(self) -> None:
        node = TraceNode(
            signature=MethodSignature(
                "Service",
                "call",
                [
                    ParameterCapture("customerId", "cust-1"),
                    ParameterCapture("amount", "99.5"),
                ],
            ),
            outcome=Returned("100"),
        )
        rendered = _RENDERER.render(TraceTree([node]))
        assert rendered == "- Service.call(customerId, amount) → value\n"
        assert "cust-1" not in rendered
        assert "99.5" not in rendered

    def test_control_characters_in_identifiers_are_sanitized(self) -> None:
        node = _node(class_name="Ser\x07vice", method_name="ca\x07ll", params=["par\x07am"])
        rendered = _RENDERER.render(TraceTree([node]))
        assert "\x07" not in rendered


class TestNesting:
    def test_children_indent_two_spaces_per_depth(self) -> None:
        child = _node(method_name="child")
        parent = _node(method_name="parent", children=[child])
        rendered = _RENDERER.render(TraceTree([parent]))
        assert rendered == "- Service.parent()\n  - Service.child()\n"

    def test_render_document_prepends_the_scenario_header(self) -> None:
        tree = TraceTree([_node()])
        document = _RENDERER.render_document(tree, "customerPlacesOrder")
        assert document.startswith("scenario: customerPlacesOrder\n\n")

    def test_header_is_sanitized_but_not_humanized(self) -> None:
        tree = TraceTree([])
        document = _RENDERER.render_document(tree, "already humanized title")
        assert document == "scenario: already humanized title\n\n"


class TestConcurrencyGrouping:
    def _member(self, class_name: str, method_name: str, group_id: str = "g1") -> TraceNode:
        return _node(
            class_name=class_name,
            method_name=method_name,
            outcome=Returned("x"),
            concurrency=ConcurrencyInfo(group_id, ConcurrencyKind.FORK_JOIN),
        )

    def test_fork_group_renders_marker_with_count(self) -> None:
        members = [self._member("Bravo", "run"), self._member("Alpha", "run")]
        rendered = _RENDERER.render(TraceTree(members))
        assert rendered.splitlines()[0] == "~ fork [2]"

    def test_fork_group_members_sort_by_class_and_method(self) -> None:
        members = [self._member("Bravo", "run"), self._member("Alpha", "run")]
        rendered = _RENDERER.render(TraceTree(members))
        lines = rendered.splitlines()
        assert lines[1] == "  - Alpha.run() → value"
        assert lines[2] == "  - Bravo.run() → value"

    def test_async_group_renders_its_own_marker(self) -> None:
        members = [
            _node(
                class_name="A",
                method_name="run",
                outcome=Returned("x"),
                concurrency=ConcurrencyInfo("g1", ConcurrencyKind.ASYNC),
            ),
            _node(
                class_name="B",
                method_name="run",
                outcome=Returned("x"),
                concurrency=ConcurrencyInfo("g1", ConcurrencyKind.ASYNC),
            ),
        ]
        rendered = _RENDERER.render(TraceTree(members))
        assert rendered.splitlines()[0] == "~ async [2]"

    def test_fire_and_forget_renders_marker_then_children_as_siblings(self) -> None:
        launcher = _node(
            method_name="launch",
            children=[_node(method_name="work", outcome=Returned("x"))],
            concurrency=ConcurrencyInfo("g1", ConcurrencyKind.FIRE_AND_FORGET),
        )
        rendered = _RENDERER.render(TraceTree([launcher]))
        assert rendered == "~ fire-and-forget\n  - Service.work() → value\n"

    def test_fire_and_forget_with_no_children_renders_only_the_marker(self) -> None:
        launcher = _node(
            method_name="launch", concurrency=ConcurrencyInfo("g1", ConcurrencyKind.FIRE_AND_FORGET)
        )
        rendered = _RENDERER.render(TraceTree([launcher]))
        assert rendered == "~ fire-and-forget\n"

    def test_sequential_sibling_between_two_groups_is_unaffected(self) -> None:
        group_a = [self._member("A", "run", "g1"), self._member("B", "run", "g1")]
        plain = _node(method_name="middle", outcome=Returned("x"))
        group_b = [self._member("C", "run", "g2"), self._member("D", "run", "g2")]
        rendered = _RENDERER.render(TraceTree([*group_a, plain, *group_b]))
        lines = rendered.splitlines()
        assert lines[0] == "~ fork [2]"
        assert "- Service.middle() → value" in lines
        assert lines.count("~ fork [2]") == 2


class TestWalkLimits:
    def test_cyclic_tree_renders_a_marker_instead_of_recursing_forever(self) -> None:
        cyclic = TraceNode(signature=MethodSignature("Service", "loop", []), children=[])
        cyclic.children.append(cyclic)  # a hand-built cycle: nothing in the dataclass prevents this
        rendered = _RENDERER.render(TraceTree([cyclic]))
        # The first occurrence renders normally; the walk only recognizes the second occurrence
        # (found while descending into its own children) as already being on the current path.
        assert rendered == "- Service.loop()\n  - Service.loop() … (cycle)\n"

    def test_a_pathologically_deep_chain_stops_at_the_depth_limit(self) -> None:
        node = _node(method_name="leaf")
        for i in range(150):
            node = _node(method_name=f"level{i}", children=[node])
        rendered = _RENDERER.render(TraceTree([node]))
        assert "… (depth limit)" in rendered
