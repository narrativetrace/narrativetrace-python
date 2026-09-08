# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests pinning Mermaid/PlantUML sequence-diagram tokens to the Java format."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from narrativetrace_diagrams.mermaid import MermaidSequenceDiagramRenderer
from narrativetrace_diagrams.plantuml import PlantUmlSequenceDiagramRenderer
from narrativetrace_diagrams.text import diagram_message

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import CYCLE_MARKER, DEPTH_LIMIT_MARKER


def _node(
    cls: str,
    method: str,
    outcome: TraceOutcome | None,
    children: list[TraceNode] | None = None,
    params: list[ParameterCapture] | None = None,
) -> TraceNode:
    return TraceNode(MethodSignature(cls, method, params or []), children or [], outcome)


def _tree(*roots: TraceNode) -> TraceTree:
    return TraceTree(list(roots))


class TestMermaid:
    def test_root_self_call_and_return(self) -> None:
        out = MermaidSequenceDiagramRenderer().render(
            _tree(_node("OrderService", "place", Returned("ok")))
        )
        assert "sequenceDiagram" in out
        assert "OrderService->>OrderService: place()" in out
        assert "OrderService-->>OrderService: ok" in out

    def test_child_call_and_return(self) -> None:
        child = _node("Inventory", "check", Returned("true"))
        root = _node("OrderService", "place", Returned("ok"), [child])
        out = MermaidSequenceDiagramRenderer().render(_tree(root))
        assert "OrderService->>Inventory: check()" in out
        assert "Inventory-->>OrderService: true" in out

    def test_throw_uses_solid_cross_and_type_name(self) -> None:
        child = _node("Payment", "charge", Threw(ValueError("no funds")))
        root = _node("OrderService", "place", Returned("ok"), [child])
        out = MermaidSequenceDiagramRenderer().render(_tree(root))
        assert "Payment-xOrderService: ValueError" in out
        assert "--x" not in out  # solid, not dashed

    def test_incomplete_is_note_and_no_return_arrow(self) -> None:
        out = MermaidSequenceDiagramRenderer().render(_tree(_node("Svc", "run", Incomplete())))
        assert "Note over Svc: in-flight" in out
        assert "-->>" not in out

    def test_void_return_still_emits_arrow(self) -> None:
        out = MermaidSequenceDiagramRenderer().render(_tree(_node("Svc", "run", Returned(None))))
        assert "Svc-->>Svc: null" in out

    def test_params_listed_by_name(self) -> None:
        node = _node(
            "S", "m", Returned("x"), params=[ParameterCapture("a", "1"), ParameterCapture("b", "2")]
        )
        out = MermaidSequenceDiagramRenderer().render(_tree(node))
        assert "S->>S: m(a, b)" in out


class TestMermaidAliases:
    def test_multi_capital_alias(self) -> None:
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("OrderService", "place", Returned("ok")))
        )
        assert "participant OS as OrderService" in out
        assert "OS->>OS: place()" in out

    def test_single_capital_alias(self) -> None:
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("Room", "book", Returned("ok")))
        )
        assert "participant R as Room" in out

    def test_all_lowercase_alias_is_full_name(self) -> None:
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("scheduler", "tick", Returned("ok")))
        )
        assert "participant scheduler as scheduler" in out

    def test_conflicting_aliases_get_numeric_suffix(self) -> None:
        child = _node("OtherService", "b", Returned("y"))
        root = _node("OrderService", "a", Returned("x"), [child])
        out = MermaidSequenceDiagramRenderer().render_with_aliases(_tree(root))
        assert "participant OS as OrderService" in out
        assert "participant OS2 as OtherService" in out


class TestPlantUml:
    def test_full_name_participants_and_arrows(self) -> None:
        child = _node("Payment", "charge", Threw(RuntimeError("x")))
        root = _node("OrderService", "place", Returned("ok"), [child])
        out = PlantUmlSequenceDiagramRenderer().render(_tree(root))
        assert out.startswith("@startuml")
        assert out.endswith("@enduml")
        assert "participant OrderService" in out
        assert "OrderService -> Payment: charge()" in out
        assert "Payment -[#red]-> OrderService: RuntimeError" in out
        assert "OrderService --> OrderService: ok" in out
        assert "activate" not in out  # Java parity: no lifelines by default

    def test_incomplete_hnote(self) -> None:
        out = PlantUmlSequenceDiagramRenderer().render(_tree(_node("Svc", "run", Incomplete())))
        assert "hnote over Svc : in-flight" in out
        assert "-->" not in out

    def test_lifelines_option(self) -> None:
        out = PlantUmlSequenceDiagramRenderer(lifelines=True).render(
            _tree(_node("Svc", "run", Returned("ok")))
        )
        assert "activate Svc" in out
        assert "deactivate Svc" in out


class TestQuotingAndSanitising:
    def test_special_char_names_quoted(self) -> None:
        out = MermaidSequenceDiagramRenderer().render(
            _tree(_node("Order Service", "m", Returned("x")))
        )
        assert 'participant "Order Service"' in out

    def test_qualified_name_quoted_in_plantuml(self) -> None:
        out = PlantUmlSequenceDiagramRenderer().render(
            _tree(_node("com.example.Foo", "m", Returned("x")))
        )
        assert 'participant "com.example.Foo"' in out

    def test_newline_in_return_folded(self) -> None:
        out = MermaidSequenceDiagramRenderer().render(
            _tree(_node("S", "m", Returned("a\nclick X")))
        )
        # value stays on one line; no injected directive line
        assert "\nclick X" not in out
        assert "S-->>S: a click X" in out

    @given(st.text())
    def test_diagram_message_folds_all_controls(self, text: str) -> None:
        out = diagram_message(text)
        assert not any(ord(c) <= 0x1F or 0x7F <= ord(c) <= 0x9F for c in out)


class TestMetadataInjection:
    """Adversarial-audit mirror (2026-09-02): a control character, quote, or `%%` in
    class/method/parameter/exception-type-name metadata must not add a line, break out of a
    quoted identifier, or open a Mermaid comment. Structural assertions (line count, quote
    balance), not substring checks -- the payload IS the class name, so it is expected to appear.
    """

    def test_mermaid_newline_in_class_name_adds_no_line(self) -> None:
        safe = MermaidSequenceDiagramRenderer().render(_tree(_node("Order", "m", Returned("x"))))
        hostile = MermaidSequenceDiagramRenderer().render(
            _tree(_node("Order\nclick X", "m", Returned("x")))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_mermaid_newline_in_method_name_adds_no_line(self) -> None:
        safe = MermaidSequenceDiagramRenderer().render(_tree(_node("S", "m", Returned("x"))))
        hostile = MermaidSequenceDiagramRenderer().render(
            _tree(_node("S", "m\nclick X", Returned("x")))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_mermaid_newline_in_parameter_name_adds_no_line(self) -> None:
        safe = MermaidSequenceDiagramRenderer().render(
            _tree(_node("S", "m", Returned("x"), params=[ParameterCapture("a", "1")]))
        )
        hostile = MermaidSequenceDiagramRenderer().render(
            _tree(_node("S", "m", Returned("x"), params=[ParameterCapture("a\nclick X", "1")]))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_mermaid_newline_in_exception_type_name_adds_no_line(self) -> None:
        safe = MermaidSequenceDiagramRenderer().render(
            _tree(_node("S", "m", Threw(RuntimeError("x"))))
        )
        hostile = MermaidSequenceDiagramRenderer().render(
            _tree(_node("S", "m", Threw(_renamed_exception("Evil\nclick X"))))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_mermaid_quote_in_class_name_does_not_break_out_of_the_quoted_participant(
        self,
    ) -> None:
        out = MermaidSequenceDiagramRenderer().render(
            _tree(_node('Order"; drop', "m", Returned("x")))
        )
        participant_lines = [line for line in out.splitlines() if "participant" in line]
        assert len(participant_lines) == 1
        inner = participant_lines[0].split("participant", 1)[1].strip()
        assert inner.startswith('"') and inner.endswith('"')
        assert '"' not in inner[1:-1]

    def test_mermaid_percent_percent_in_class_name_is_not_a_comment_opener(self) -> None:
        out = MermaidSequenceDiagramRenderer().render(
            _tree(_node("S%%comment", "m", Returned("x")))
        )
        assert "%%" not in out

    def test_mermaid_empty_class_name_renders_unnamed_marker_not_a_bare_line(self) -> None:
        out = MermaidSequenceDiagramRenderer().render(_tree(_node("", "m", Returned("x"))))
        assert "participant \n" not in out
        assert "<unnamed>" in out

    def test_plantuml_newline_in_method_name_adds_no_line(self) -> None:
        safe = PlantUmlSequenceDiagramRenderer().render(_tree(_node("S", "m", Returned("x"))))
        hostile = PlantUmlSequenceDiagramRenderer().render(
            _tree(_node("S", "m\n!include /etc/passwd", Returned("x")))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_plantuml_newline_in_parameter_name_adds_no_line(self) -> None:
        safe = PlantUmlSequenceDiagramRenderer().render(
            _tree(_node("S", "m", Returned("x"), params=[ParameterCapture("a", "1")]))
        )
        hostile = PlantUmlSequenceDiagramRenderer().render(
            _tree(
                _node("S", "m", Returned("x"), params=[ParameterCapture("a\n!include evil", "1")])
            )
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_plantuml_newline_in_exception_type_name_adds_no_line(self) -> None:
        safe = PlantUmlSequenceDiagramRenderer().render(
            _tree(_node("S", "m", Threw(RuntimeError("x"))))
        )
        hostile = PlantUmlSequenceDiagramRenderer().render(
            _tree(_node("S", "m", Threw(_renamed_exception("Evil\n!include evil"))))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_plantuml_quote_in_class_name_does_not_break_out_of_the_quoted_participant(
        self,
    ) -> None:
        out = PlantUmlSequenceDiagramRenderer().render(
            _tree(_node('Order"\n!include evil', "m", Returned("x")))
        )
        participant_lines = [line for line in out.splitlines() if line.startswith("participant")]
        assert len(participant_lines) == 1
        inner = participant_lines[0].removeprefix("participant ").strip()
        assert inner.startswith('"') and inner.endswith('"')
        assert '"' not in inner[1:-1]

    def test_plantuml_empty_class_name_renders_unnamed_marker_not_a_bare_line(self) -> None:
        out = PlantUmlSequenceDiagramRenderer().render(_tree(_node("", "m", Returned("x"))))
        assert "participant \n" not in out
        assert "<unnamed>" in out


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): both renderers used unbounded native recursion with no
    depth bound or cycle guard -- both a cycle and a pathologically deep chain crashed with an
    uncaught RecursionError."""

    _RENDERERS = (
        ("mermaid", MermaidSequenceDiagramRenderer()),
        ("plantuml", PlantUmlSequenceDiagramRenderer()),
    )

    @staticmethod
    def _chain(n: int) -> TraceNode:
        node = _node("S", "leaf", Returned("x"))
        for _ in range(n):
            node = _node("S", "wrap", Returned("x"), [node])
        return node

    def test_a_self_referential_node_does_not_crash_either_renderer(self) -> None:
        node = _node("S", "self", Returned("x"))
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        for name, renderer in self._RENDERERS:
            out = renderer.render(_tree(node))  # must not raise RecursionError
            assert CYCLE_MARKER in out, name

    def test_a_ten_thousand_deep_chain_is_truncated_not_crashed(self) -> None:
        chain = self._chain(10_000)
        for name, renderer in self._RENDERERS:
            out = renderer.render(_tree(chain))  # must not raise RecursionError
            assert DEPTH_LIMIT_MARKER in out, name

    def test_mermaid_alias_rendering_also_bounds_participant_collection(self) -> None:
        chain = self._chain(10_000)
        out = MermaidSequenceDiagramRenderer().render_with_aliases(_tree(chain))
        assert isinstance(out, str)  # must not raise RecursionError


def _renamed_exception(name: str) -> Exception:
    exc_type = type("Evil", (Exception,), {})
    exc_type.__name__ = name
    instance = exc_type()
    assert isinstance(instance, Exception)
    return instance
