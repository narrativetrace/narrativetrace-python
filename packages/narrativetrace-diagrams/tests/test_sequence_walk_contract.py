# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The invariant composition is supposed to guarantee: whichever grammar
:func:`sequence_walk.render_sequence` is given, the walk emits exactly one call arrow and exactly
one outcome per node it visits or stops at -- never more, never fewer, whatever the tree's shape
or the metadata's content.

``test_diagrams.py`` already pins each grammar's own output text; this module pins the shared
traversal contract those two grammars can never diverge on, by counting hook invocations rather
than parsing rendered text -- parsing would be fooled by the hostile-metadata cases below, where
the trace-derived text legitimately contains arrow-like substrings.

The "deep chain" depth is picked to exceed this runtime's own
:data:`narrativetrace.tree_walk.MAX_DEPTH` (100) -- unlike the Java reference's 10,000, so its
own equivalent case (``deepChain(5_000)``) does not map here: at Python's bound, any chain deeper
than 100 truncates to the same 101-node shape (100 visited normally, 1 stopped-at), so the exact
depth beyond that bound is not load-bearing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from narrativetrace_diagrams.diagram_label import DiagramLabel
from narrativetrace_diagrams.mermaid import MermaidSequenceGrammar
from narrativetrace_diagrams.plantuml import PlantUmlSequenceGrammar
from narrativetrace_diagrams.sequence_grammar import LimitReason, SequenceGrammar
from narrativetrace_diagrams.sequence_walk import render_sequence

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree_walk import TreeWalk

PLAIN_LABEL = DiagramLabel.quoted_identifier


@dataclass
class _CountingGrammar:
    """Counts how many times each hook fired, while still producing the real grammar's output."""

    delegate: SequenceGrammar
    call_arrows: int = field(default=0, init=False)
    returns: int = field(default=0, init=False)
    throws: int = field(default=0, init=False)
    incompletes: int = field(default=0, init=False)
    limited_notes: int = field(default=0, init=False)

    def outcomes(self) -> int:
        return self.returns + self.throws + self.incompletes

    def header(self) -> str:
        return self.delegate.header()

    def participant(self, label: DiagramLabel) -> str:
        return self.delegate.participant(label)

    def call_arrow(
        self, caller: DiagramLabel, target: DiagramLabel, signature: DiagramLabel
    ) -> str:
        self.call_arrows += 1
        return self.delegate.call_arrow(caller, target, signature)

    def activate(self, target: DiagramLabel) -> str:
        return self.delegate.activate(target)

    def return_arrow(
        self, target: DiagramLabel, caller: DiagramLabel, message: DiagramLabel
    ) -> str:
        self.returns += 1
        return self.delegate.return_arrow(target, caller, message)

    def throw_arrow(
        self, target: DiagramLabel, caller: DiagramLabel, exception_type: DiagramLabel
    ) -> str:
        self.throws += 1
        return self.delegate.throw_arrow(target, caller, exception_type)

    def deactivate(self, target: DiagramLabel) -> str:
        return self.delegate.deactivate(target)

    def incomplete(self, target: DiagramLabel) -> str:
        self.incompletes += 1
        return self.delegate.incomplete(target)

    def limited_note(self, target: DiagramLabel, reason: LimitReason) -> str:
        self.limited_notes += 1
        return self.delegate.limited_note(target, reason)

    def footer(self) -> str:
        return self.delegate.footer()


def _leaf(class_name: str, method_name: str, children: list[TraceNode]) -> TraceNode:
    return TraceNode(MethodSignature(class_name, method_name, []), children, Returned('"ok"'))


def _deep_chain(depth: int) -> TraceNode:
    current = _leaf("Recursive", "bottom", [])
    for i in range(depth):
        current = _leaf("Recursive", f"call{i}", [current])
    return current


def _cyclic_ring() -> TraceNode:
    child_holder: list[TraceNode] = []
    b = _leaf("Ring", "b", child_holder)
    a = _leaf("Ring", "a", [b])
    child_holder.append(a)
    return a


QUOTE_AND_BREAK = (
    'Victim"\nparticipant InjectedActor\nclick InjectedActor href "https://attacker.example"'
)
NOTE_FORGERY = "Victim\nnote over Victim: forged\n"
ARROW_LOOKALIKE = "->>-->>-x-> --> -[#red]->"


def _hostile_metadata(hostile: str) -> TraceNode:
    return TraceNode(
        MethodSignature(hostile, hostile, [ParameterCapture(hostile, '"v"')]),
        [],
        Threw(RuntimeError(hostile)),
    )


HOSTILE_TREES = [
    pytest.param(_deep_chain(5_000), 101, id="deep chain"),
    pytest.param(_cyclic_ring(), 3, id="cyclic ring"),
    pytest.param(_hostile_metadata(QUOTE_AND_BREAK), 1, id="quote+break metadata"),
    pytest.param(_hostile_metadata(NOTE_FORGERY), 1, id="note forgery metadata"),
    pytest.param(_hostile_metadata(ARROW_LOOKALIKE), 1, id="arrow-lookalike metadata"),
]


def _node_count(root: TraceNode) -> int:
    """How many nodes a plain :class:`TreeWalk` actually visits or stops at, independent of any
    grammar."""
    walk = TreeWalk()
    count = 0

    def _visit(node: TraceNode) -> None:
        nonlocal count
        count += 1
        if walk.stop_reason(node) is None:
            walk.enter(node)
            try:
                for child in node.children:
                    _visit(child)
            finally:
                walk.exit(node)

    _visit(root)
    return count


def _limit_count(root: TraceNode) -> int:
    """How many of those nodes the walk stopped at instead of visiting (a cycle or the depth
    cap)."""
    walk = TreeWalk()
    count = 0

    def _visit(node: TraceNode) -> None:
        nonlocal count
        if walk.stop_reason(node) is not None:
            count += 1
            return
        walk.enter(node)
        try:
            for child in node.children:
                _visit(child)
        finally:
            walk.exit(node)

    _visit(root)
    return count


def _assert_one_arrow_and_one_outcome_per_node(
    root: TraceNode, expected_nodes: int, real: SequenceGrammar
) -> None:
    assert _node_count(root) == expected_nodes

    counting = _CountingGrammar(real)
    render_sequence(root, counting, PLAIN_LABEL, [], TreeWalk())

    assert counting.call_arrows == expected_nodes, "call arrows"
    assert counting.outcomes() == expected_nodes, "outcomes (return + throw + incomplete)"
    assert counting.limited_notes == _limit_count(root), "limited notes"


class TestSequenceWalkContract:
    @pytest.mark.parametrize(("root", "expected_nodes"), HOSTILE_TREES)
    def test_mermaid_emits_exactly_one_call_arrow_and_one_outcome_per_node(
        self, root: TraceNode, expected_nodes: int
    ) -> None:
        _assert_one_arrow_and_one_outcome_per_node(root, expected_nodes, MermaidSequenceGrammar())

    @pytest.mark.parametrize(("root", "expected_nodes"), HOSTILE_TREES)
    def test_plantuml_emits_exactly_one_call_arrow_and_one_outcome_per_node(
        self, root: TraceNode, expected_nodes: int
    ) -> None:
        _assert_one_arrow_and_one_outcome_per_node(
            root, expected_nodes, PlantUmlSequenceGrammar(lifelines=False)
        )

    def test_both_grammars_agree_on_node_count_for_the_same_hostile_tree(self) -> None:
        root = _hostile_metadata(QUOTE_AND_BREAK)

        mermaid = _CountingGrammar(MermaidSequenceGrammar())
        plantuml = _CountingGrammar(PlantUmlSequenceGrammar(lifelines=False))
        render_sequence(root, mermaid, PLAIN_LABEL, [], TreeWalk())
        render_sequence(root, plantuml, PLAIN_LABEL, [], TreeWalk())

        assert mermaid.call_arrows == plantuml.call_arrows
        assert mermaid.outcomes() == plantuml.outcomes()
