# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-206, the numeric question (Python twin of Java ``ValueRendererNumericLeafSecretTest``): a
number's own text is shape-scanned like a string's.

INTENT: a 16-digit card number held as an ``int`` is the realistic leak -- the value-shape axis
asks what the bytes say, and the bytes of ``4111111111111111`` say card number whatever the type
holding them. Only a Luhn-valid number of 12 or more digits is withheld; a number that fails the
checksum, or is shorter, prints as before.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.rendering import ValueRenderer
from narrativetrace.template import _scalar_text
from narrativetrace.values import IntVal, StringVal

_CARD = 4111111111111111
_MARKER = "[REDACTED]"


@dataclass
class _Holder:
    amount: int


class TestAnIntHoldingACardNumber:
    def test_is_withheld_on_the_flat_path(self) -> None:
        assert ValueRenderer().render(_CARD) == _MARKER

    def test_is_withheld_on_the_structured_path(self) -> None:
        assert ValueRenderer().render_structured(_CARD) == StringVal(_MARKER)

    def test_is_withheld_as_a_field_and_a_collection_element(self) -> None:
        renderer = ValueRenderer()

        assert str(_CARD) not in renderer.render(_Holder(_CARD))
        assert str(_CARD) not in renderer.render([_CARD])
        assert str(_CARD) not in repr(renderer.render_structured(_Holder(_CARD)))
        assert str(_CARD) not in repr(renderer.render_structured({"k": _CARD}))

    def test_is_withheld_from_a_narration(self) -> None:
        assert _scalar_text(_CARD) == _MARKER

    def test_is_withheld_from_a_parameter_capture(self) -> None:
        text, structured, _ = ValueRenderer().render_for_capture(_CARD)

        assert text == _MARKER
        assert structured == StringVal(_MARKER)


class TestOrdinaryNumbersAreUntouched:
    def test_an_int_that_fails_the_checksum_stays_visible(self) -> None:
        renderer = ValueRenderer()

        assert renderer.render(4111111111111112) == "4111111111111112"
        assert renderer.render_structured(4111111111111112) == IntVal(4111111111111112)
        assert renderer.render(1_700_000_000_001) == "1700000000001"

    def test_small_ints_floats_and_bools_print_as_before(self) -> None:
        renderer = ValueRenderer()

        assert renderer.render(42) == "42"
        assert renderer.render(3.5) == "3.5"
        assert renderer.render(True) == "True"
        assert renderer.render_structured(42) == IntVal(42)
        assert _scalar_text(42) == "42"
