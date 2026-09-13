# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``DiagramLabel`` is supposed to make "no raw trace string reaches a grammar hook" a structural
fact rather than a convention. This module is the receipt.

Unlike the Java reference (a private constructor the compiler enforces, checked by reflecting on
``SequenceGrammar``'s declared parameter types), Python has no private constructor -- so
``TestDiagramLabelConstructionIsClosed`` proves the runtime side of the same claim (direct
construction actually raises) and ``TestSequenceGrammarShape`` proves the static side, by
inspecting :class:`~narrativetrace_diagrams.sequence_grammar.SequenceGrammar`'s own type
annotations rather than any one call site.
"""

from __future__ import annotations

from typing import get_type_hints

import pytest
from narrativetrace_diagrams.diagram_label import DiagramLabel
from narrativetrace_diagrams.sequence_grammar import LimitReason, SequenceGrammar

_ALLOWED_PARAMETER_TYPES = {DiagramLabel, LimitReason}


def _hook_names() -> list[str]:
    return [
        name
        for name, member in vars(SequenceGrammar).items()
        if callable(member) and not name.startswith("_")
    ]


class TestSequenceGrammarShape:
    @pytest.mark.parametrize("hook_name", _hook_names())
    def test_no_hook_accepts_a_raw_string(self, hook_name: str) -> None:
        hints = get_type_hints(getattr(SequenceGrammar, hook_name))
        hints.pop("return", None)
        assert str not in hints.values(), (
            f"SequenceGrammar.{hook_name} must not take a raw str -- trace-derived text must "
            "arrive as a DiagramLabel"
        )

    @pytest.mark.parametrize("hook_name", _hook_names())
    def test_every_hook_parameter_is_a_diagram_label_or_a_limit_reason(
        self, hook_name: str
    ) -> None:
        hints = get_type_hints(getattr(SequenceGrammar, hook_name))
        hints.pop("return", None)
        for parameter_name, parameter_type in hints.items():
            assert parameter_type in _ALLOWED_PARAMETER_TYPES, (
                f"SequenceGrammar.{hook_name} parameter {parameter_name!r} has unexpected type "
                f"{parameter_type!r}"
            )

    @pytest.mark.parametrize("hook_name", _hook_names())
    def test_every_hook_returns_a_string(self, hook_name: str) -> None:
        hints = get_type_hints(getattr(SequenceGrammar, hook_name))
        assert hints.get("return") is str, (
            f"SequenceGrammar.{hook_name} should return the composed diagram text"
        )

    def test_there_are_ten_hooks(self) -> None:
        # header, participant, call_arrow, activate, return_arrow, throw_arrow, deactivate,
        # incomplete, limited_note, footer -- eight mirror the Java reference's SequenceGrammar,
        # activate/deactivate are PlantUML-lifelines-only extras with no Java counterpart.
        assert len(_hook_names()) == 10


class TestDiagramLabelConstructionIsClosed:
    def test_direct_construction_raises(self) -> None:
        with pytest.raises(TypeError):
            DiagramLabel("hostile")

    def test_direct_construction_with_a_forged_token_still_raises(self) -> None:
        with pytest.raises(TypeError):
            DiagramLabel("hostile", object())

    def test_identifier_factory_produces_a_label(self) -> None:
        assert DiagramLabel.identifier("Order").text == "Order"

    def test_quoted_identifier_factory_produces_a_label(self) -> None:
        assert DiagramLabel.quoted_identifier("Order Service").text == '"Order Service"'

    def test_message_factory_produces_a_label(self) -> None:
        assert DiagramLabel.message("a\nb").text == "a b"

    def test_alias_factory_produces_a_label(self) -> None:
        assert DiagramLabel.alias("Order").text == "Order"

    def test_alias_factory_strips_every_character_that_is_not_a_letter_digit_or_underscore(
        self,
    ) -> None:
        assert DiagramLabel.alias('a->>b: c"d').text == "abcd"

    def test_alias_factory_never_returns_an_empty_token(self) -> None:
        assert DiagramLabel.alias("").text
        assert DiagramLabel.alias('->>:"').text

    def test_with_parameters_composes_without_reopening_the_sanitizer(self) -> None:
        method = DiagramLabel.identifier("place")
        params = [DiagramLabel.identifier("a"), DiagramLabel.identifier("b")]
        assert method.with_parameters(params).text == "place(a, b)"

    def test_aliased_as_composes_without_reopening_the_sanitizer(self) -> None:
        alias = DiagramLabel.identifier("OS")
        display = DiagramLabel.quoted_identifier("OrderService")
        assert alias.aliased_as(display).text == "OS as OrderService"
