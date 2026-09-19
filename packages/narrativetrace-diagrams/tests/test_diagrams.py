# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests pinning Mermaid/PlantUML sequence-diagram tokens to the Java format."""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st
from narrativetrace_diagrams.mermaid import MermaidSequenceDiagramRenderer
from narrativetrace_diagrams.plantuml import PlantUmlSequenceDiagramRenderer
from narrativetrace_diagrams.text import alias_token, diagram_message

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


_BARE_ALIAS = re.compile(r"^[^\s]+$")
_WORD_ALIAS = re.compile(r"^\w+$", re.UNICODE)


class TestMermaidAliasHostileClassNames:
    """The alias-mode fallback (no uppercase letters to extract) used to pass the raw class name
    straight through as the bare token on every arrow line and participant declaration -- grammar
    position, not text position. A space split the arrow into the wrong number of tokens, ``->>``
    or ``:`` forged a second arrow or an early message boundary, and two names that only differ in
    a character :func:`~narrativetrace_diagrams.text.identifier` folds later (``"`` vs ``'``)
    collided into one alias unnoticed, because the collision check ran on the pre-sanitized name.
    """

    @staticmethod
    def _alias_of(out: str) -> str:
        line = next(line for line in out.splitlines() if line.strip().startswith("participant"))
        return line.strip().removeprefix("participant ").split(" as ", 1)[0]

    def test_arrow_token_in_an_all_lowercase_class_name_does_not_split_the_arrow_line(
        self,
    ) -> None:
        safe = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("svc", "m", Returned("ok")))
        )
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("a->>b", "m", Returned("ok")))
        )
        assert out.count("\n") == safe.count("\n")
        assert _WORD_ALIAS.match(self._alias_of(out))

    def test_colon_in_an_all_lowercase_class_name_does_not_shift_the_message_boundary(
        self,
    ) -> None:
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("a:b", "m", Returned("ok")))
        )
        assert _WORD_ALIAS.match(self._alias_of(out))
        assert "a:b->>a:b" not in out

    def test_space_in_an_all_lowercase_class_name_does_not_split_the_bare_token(self) -> None:
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("a b", "m", Returned("ok")))
        )
        assert _BARE_ALIAS.match(self._alias_of(out))
        assert _WORD_ALIAS.match(self._alias_of(out))

    def test_double_quote_in_an_all_lowercase_class_name_does_not_close_the_display_quote_early(
        self,
    ) -> None:
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node('a"b', "m", Returned("ok")))
        )
        assert _WORD_ALIAS.match(self._alias_of(out))

    def test_empty_class_name_gets_a_nonempty_bare_alias(self) -> None:
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("", "m", Returned("ok")))
        )
        alias = self._alias_of(out)
        assert alias
        assert _WORD_ALIAS.match(alias)

    def test_quote_variants_that_sanitize_to_the_same_token_still_get_distinct_aliases(
        self,
    ) -> None:
        # `a"b` and `a'b` both reduce to the bare token `ab`; the collision check must catch this
        # even though the two raw names look distinct before sanitization.
        child = _node("a'b", "m2", Returned("y"))
        root = _node('a"b', "m1", Returned("x"), [child])
        out = MermaidSequenceDiagramRenderer().render_with_aliases(_tree(root))
        participant_lines = [
            line.strip() for line in out.splitlines() if line.strip().startswith("participant")
        ]
        aliases = [
            line.removeprefix("participant ").split(" as ", 1)[0] for line in participant_lines
        ]
        assert len(aliases) == 2
        assert len(set(aliases)) == 2, "distinct classes must not collapse onto one alias"

    def test_mermaid_reserved_word_as_a_class_name_gets_a_suffixed_alias(self) -> None:
        # Before the 2026-09-13 fix: a class named `end` (or `participant`, `loop`, ...) yielded
        # that word, unchanged, as its own alias -- a bare token Mermaid's grammar reserves for
        # closing a loop/alt/opt/rect/critical/box block or opening a declaration, which the
        # parser rejects outright rather than renders. `alias_token` now suffixes a trailing `_`
        # on a case-insensitive collision with the reserved set sourced from
        # sequenceDiagram.jison (mermaid-js/mermaid, verified 2026-09-13).
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("end", "m", Returned("ok")))
        )
        assert "participant end_ as end" in out
        assert "end_->>end_: m()" in out

    def test_mermaid_reserved_word_alias_collision_is_case_insensitive(self) -> None:
        # Mermaid's lexer declares `%options case-insensitive`, so `alias_token` (the fallback
        # `_build_aliases` reaches for a class name with no uppercase letters to extract from)
        # must match a reserved word regardless of the class name's original case. Exercised
        # directly: a class name mixing case (e.g. "Loop") has an uppercase letter and takes the
        # `_extract_upper` path instead, so it never reaches `alias_token`'s reserved-word check.
        assert alias_token("loop") == "loop_"
        assert alias_token("LOOP") == "LOOP_"
        assert alias_token("Loop") == "Loop_"


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


class TestPlainModeReservedWords:
    """Reproduces the OPEN item from the 2026-09-13 alias-mode review, in PLAIN mode: a class
    named a bare Mermaid or PlantUML sequence-diagram keyword (``end``) used to render as that
    word, unquoted -- ``quote_if_needed`` quoted only on ``". - : < > " space"``, never on a
    reserved-word collision, so ``participant end``/``end->>end: run()`` (Mermaid) and
    ``participant end``/``end -> end: run()`` (PlantUML) reached output the grammar rejects
    rather than renders.

    Mermaid: verified against ``sequenceDiagram.jison``'s keyword lexer rules (the same set
    :data:`~narrativetrace_diagrams.text._MERMAID_RESERVED_ALIASES` cites) and the official docs'
    own guidance for "end" ("one must use parentheses(), quotation marks, or brackets... to
    enclose the word 'end'" -- mermaid.js.org/syntax/sequenceDiagram.html). PlantUML: verified
    against plantuml.com/sequence-diagram, which documents quoting as the escape for exactly this
    collision and shows it used in a message/arrow line, not only a declaration (``"Bob()" ->
    "This is very\\nlong" as Long``).

    Unlike alias mode's underscore suffix, plain mode keeps the exact class name as the visible
    token, just quoted -- ``quote_if_needed``'s existing mechanism for any other grammar-breaking
    character, now shared by ``plain_mode_token``.
    """

    def test_mermaid_bare_reserved_word_participant_is_quoted(self) -> None:
        out = MermaidSequenceDiagramRenderer().render(_tree(_node("end", "run", Returned("true"))))
        assert 'participant "end"' in out
        assert '"end"->>"end": run()' in out
        assert "participant end\n" not in out

    def test_plantuml_bare_reserved_word_participant_is_quoted(self) -> None:
        out = PlantUmlSequenceDiagramRenderer().render(_tree(_node("end", "run", Returned("true"))))
        assert 'participant "end"' in out
        assert '"end" -> "end": run()' in out
        assert "participant end\n" not in out

    def test_plantuml_quotes_a_mermaid_only_reserved_word_too(self) -> None:
        # "over" is a Mermaid sequence-diagram keyword, not a PlantUML one -- plain_mode_token is
        # shared by both grammars and applies the union of their hazards, so PlantUML quotes it
        # too (harmless here, consistent with `identifier`'s own union-of-hazards design).
        out = PlantUmlSequenceDiagramRenderer().render(
            _tree(_node("over", "run", Returned("true")))
        )
        assert 'participant "over"' in out

    def test_mermaid_alias_mode_display_name_keeps_a_reserved_word_unquoted(self) -> None:
        # `plain_mode_token` must never leak into alias mode's "as" display name -- that path is
        # documented (and pinned above) to keep a reserved word unescaped, via `quoted_identifier`.
        out = MermaidSequenceDiagramRenderer().render_with_aliases(
            _tree(_node("end", "run", Returned("true")))
        )
        assert "participant end_ as end" in out


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

    # Builds and walks a 10,000-deep chain through both renderers. HANG GUARD, not a timing
    # assertion -- the test only checks both renderers show the depth-limit marker, never a
    # duration, so the budget is the documented 10s floor, not a multiple of a timing sample
    # (release retrospective rule 3 refinement, Pro ledger #129: "5x a contended sample" still
    # makes wall-clock a test input -- TestParseCacheIsBounded went red under scheduler
    # starvation at a 0.8s sample-derived budget).
    @pytest.mark.timeout(10.0)
    def test_a_ten_thousand_deep_chain_is_truncated_not_crashed(self) -> None:
        chain = self._chain(10_000)
        for name, renderer in self._RENDERERS:
            out = renderer.render(_tree(chain))  # must not raise RecursionError
            assert DEPTH_LIMIT_MARKER in out, name

    # Builds a 10,000-deep chain and collects Mermaid aliases for it. HANG GUARD, not a timing
    # assertion -- the test only checks the result is a string, never a duration, so the budget
    # is the documented 10s floor, not a multiple of a timing sample (release retrospective
    # rule 3 refinement, Pro ledger #129).
    @pytest.mark.timeout(10.0)
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
