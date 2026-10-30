# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-206 (family twin of Swift B-200, TypeScript B-206): a leaf rendered through its own string
conversion is checked by SHAPE on the raw text before sanitise and cap, like every other string --
on the flat and the structured path, as a root and as a field."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

import pytest

from narrativetrace import narrative_summary
from narrativetrace.rendering import ValueRenderer
from narrativetrace.template import _scalar_text

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl"
CARD = "4111111111111111"
MARKER = "[REDACTED]"


def _leaf(text: str) -> PurePosixPath:
    return PurePosixPath(text)


def _enum(text: str) -> Enum:
    class Token(Enum):
        ONE = 1

        def __str__(self) -> str:
            return text

    return Token.ONE


class _Summarised:
    def __init__(self, text: str) -> None:
        self._text = text

    @narrative_summary
    def summary(self) -> str:
        return self._text


@dataclass
class _Holder:
    when: Any


def _structured(value: object) -> str:
    return json.dumps(repr(ValueRenderer().render_structured(value)))


_MAKERS = [_leaf, _enum, _Summarised]


@pytest.mark.parametrize("secret", [JWT, CARD])
@pytest.mark.parametrize("make", _MAKERS)
def test_flat_root_is_the_marker(make: Any, secret: str) -> None:
    assert ValueRenderer().render(make(secret)) == MARKER


@pytest.mark.parametrize("secret", [JWT, CARD])
@pytest.mark.parametrize("make", _MAKERS)
def test_flat_field_and_dict_value_never_in_clear(make: Any, secret: str) -> None:
    renderer = ValueRenderer()
    assert secret not in renderer.render(_Holder(make(secret)))
    assert secret not in renderer.render({"k": make(secret)})
    assert secret not in renderer.render([make(secret)])


@pytest.mark.parametrize("secret", [JWT, CARD])
@pytest.mark.parametrize("make", _MAKERS)
def test_structured_never_in_clear(make: Any, secret: str) -> None:
    assert secret not in _structured(make(secret))
    assert MARKER in _structured(make(secret))
    assert secret not in _structured(_Holder(make(secret)))


@pytest.mark.parametrize("secret", [JWT, CARD])
def test_dict_key_leaf_text_never_in_clear(secret: str) -> None:
    renderer = ValueRenderer()
    assert secret not in renderer.render({_leaf(secret): 1})
    assert secret not in _structured({_leaf(secret): 1})


@pytest.mark.parametrize("secret", [JWT, CARD])
def test_narration_enum_text_is_the_marker(secret: str) -> None:
    assert _scalar_text(_enum(secret)) == MARKER


@pytest.mark.parametrize("make", _MAKERS)
def test_plain_leaf_text_is_unchanged(make: Any) -> None:
    assert "plain text" in ValueRenderer().render(make("plain text"))


@pytest.mark.parametrize("make", _MAKERS)
def test_control_characters_are_still_escaped(make: Any) -> None:
    rendered = ValueRenderer().render(make("a\nb"))
    assert "\n" not in rendered
    assert "a" in rendered
