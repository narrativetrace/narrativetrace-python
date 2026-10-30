# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The channel the value-shape axis did not reach, held to the same standard as every other.

``ExceptionMessageRedactionTest`` -- the shared family test this runtime had no mirror of.
``Threw`` carries the live exception rather than text a renderer produced, so an exception message
passed no redaction axis at all until ``narrativetrace.exception_message`` became the one reading
every emitter shares. The oracle here is this package's usual one: a value that must not appear
appears in no byte of any emitter's output, and it is asserted over :data:`emitters.EMITTERS`
rather than a hand-listed set, so an emitter added there is covered the day it is added.

The core package's ``test_exception_message_sinks.py`` pins the *wording* each named emitter
prints; this pins the *containment* across all of them at once -- the two are not substitutes.

**@edgeCase** The claim is *parity*, not clairvoyance. The value axis matches a whole string --
that is what keeps its false-positive budget near zero -- so a message that merely mentions a
token inside prose is shown, exactly as the identical string is shown when it arrives as a
captured parameter. What must never differ again is the answer for the *same* bytes on two
channels.
"""

from __future__ import annotations

from emitters import every_output, metadata_for, tree_throwing
from oracles import contains_nowhere, sentinel_token

from narrativetrace.redaction import REDACTED_MARKER
from narrativetrace.rendering import ValueRenderer

_SCENARIO = "Exception message redaction"

# Public test PAN, not a real credential; the shape policy recognises these bytes.
_PAN = "4111111111111111"
_PAN_PREFIX = "41111111"

# The same digits with the last one changed: Luhn-invalid, so it is an order number, not a card.
_ORDER_NUMBER = "4111111111111112"


def _outputs(message: str) -> dict[str, str]:
    return every_output(tree_throwing(message), metadata_for(_SCENARIO))


class TestCredentialShapedMessage:
    def test_a_jwt_in_an_exception_message_is_hidden_like_a_parameter_value(self) -> None:
        sentinel = sentinel_token()
        jwt = f"eyJhbGciOiJIUzI1NiJ9.{sentinel}.c2lnbmF0dXJl"

        contains_nowhere(sentinel, _outputs(jwt))

        assert ValueRenderer().render(jwt) == REDACTED_MARKER, (
            "the same bytes as a captured parameter -- the two channels must agree"
        )

    def test_a_card_number_in_an_exception_message_reaches_no_emitter(self) -> None:
        for name, output in _outputs(_PAN).items():
            assert _PAN_PREFIX not in output, f"{name} printed the card number"


class TestOrdinaryMessage:
    """The other half of a narrow rule: an order number that fails Luhn is diagnostics, and
    blanking it would be the over-redaction teams switch a security default off for."""

    def test_a_luhn_invalid_number_still_reaches_every_narrative_emitter(self) -> None:
        outputs = _outputs(f"order {_ORDER_NUMBER} not found")
        for name in ("prose", "indented-text", "markdown-body"):
            assert _ORDER_NUMBER in outputs[name], f"{name} blanked an ordinary order number"
