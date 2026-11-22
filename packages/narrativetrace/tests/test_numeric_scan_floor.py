# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-258: the numeric value-shape scan starts at the shortest secret a matcher recognises.

INTENT: an 11-digit Brazilian CPF held as a number is the same secret as the same digits in a
``str``. The scan floor is derived from the matchers, so no bare-digit secret is shorter than
the floor that gates the scan.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from narrativetrace import national_id_shapes
from narrativetrace.rendering import _NUMERIC_SCAN_MIN_LENGTH, ValueRenderer
from narrativetrace.template import _scalar_text
from narrativetrace.values import IntVal, StringVal

_CPF = 52998224725
_MARKER = "[REDACTED]"


@pytest.mark.parametrize("number", [_CPF, Decimal(_CPF)], ids=["int", "Decimal"])
class TestAChecksumValidCpfHeldAsANumber:
    def test_is_withheld_on_the_flat_path(self, number: object) -> None:
        assert ValueRenderer().render(number) == _MARKER

    def test_is_withheld_on_the_structured_path(self, number: object) -> None:
        assert ValueRenderer().render_structured(number) == StringVal(_MARKER)

    def test_is_withheld_from_a_narration(self, number: object) -> None:
        assert _scalar_text(number) == _MARKER


class TestShortNumbersThatAreNotSecretsStayVisible:
    @pytest.mark.parametrize("number", [12345678901, 52998224726, 42, 20261110])
    def test_prints_as_before(self, number: int) -> None:
        renderer = ValueRenderer()

        assert renderer.render(number) == str(number)
        assert renderer.render_structured(number) == IntVal(number)
        assert _scalar_text(number) == str(number)


class TestTheFloorIsDerivedFromTheMatchers:
    def test_equals_the_shortest_bare_digit_matcher(self) -> None:
        assert national_id_shapes.SHORTEST_BARE_DIGIT_SECRET == 11
        assert _NUMERIC_SCAN_MIN_LENGTH == 11
