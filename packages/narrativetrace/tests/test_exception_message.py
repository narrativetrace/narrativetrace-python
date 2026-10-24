# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one reading of an exception's message every emitter shares (B-174; mirrors Java's
``ExceptionMessage``): redacted whole when its shape is a credential, control-escaped always."""

from __future__ import annotations

from narrativetrace import exception_message
from narrativetrace.redaction import REDACTED_MARKER

# Public test PAN, not a real credential; the shape policy recognises these bytes.
_PAN = "4111111111111111"


class _Unreadable(Exception):
    def __str__(self) -> str:
        raise RuntimeError("no message for you")


class TestOf:
    def test_a_missing_exception_answers_none(self) -> None:
        assert exception_message.of(None) is None

    def test_a_plain_message_passes_through(self) -> None:
        assert exception_message.of(ValueError("boom")) == "boom"

    def test_a_credential_shaped_message_is_replaced_whole_by_the_marker(self) -> None:
        assert exception_message.of(ValueError(_PAN)) == REDACTED_MARKER

    def test_control_characters_are_escaped(self) -> None:
        assert exception_message.of(ValueError("a\nb")) == "a\\nb"

    def test_a_message_that_cannot_be_read_degrades_to_the_error_literal(self) -> None:
        assert exception_message.of(_Unreadable()) == "<error>"


class TestText:
    def test_text_is_the_message(self) -> None:
        assert exception_message.text(ValueError("boom")) == "boom"

    def test_text_spells_a_missing_exception_as_null(self) -> None:
        assert exception_message.text(None) == "null"

    def test_text_redacts_too(self) -> None:
        assert exception_message.text(ValueError(_PAN)) == REDACTED_MARKER
