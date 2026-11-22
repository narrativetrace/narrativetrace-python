# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A standard-library wrapper never renders its user payload through the payload's own ``repr``.

``deque``, ``MappingProxyType``, ``ChainMap``, ``functools.partial`` and ``SimpleNamespace`` hold
application values. Rendering them through their own text would call the payload's ``__repr__``
and skip redaction by name, so each wrapper is walked instead, on both channels.
"""

from __future__ import annotations

import collections
import dataclasses
import functools
import types
from collections.abc import Callable

import pytest

from narrativetrace.rendering import ValueRenderer

SECRET = "hunter2-secret"


@dataclasses.dataclass
class Card:
    password: str


class SpyRepr:
    """Counts every call to its own text conversions; renders nothing sensitive."""

    calls = 0

    def __repr__(self) -> str:
        SpyRepr.calls += 1
        return "SPY-REPR"

    __str__ = __repr__


def _card() -> Card:
    return Card(password=SECRET)


def _deque(payload: object) -> object:
    return collections.deque([payload])


def _proxy(payload: object) -> object:
    return types.MappingProxyType({"k": payload})


def _chain(payload: object) -> object:
    return collections.ChainMap({"k": payload})


def _partial(payload: object) -> object:
    return functools.partial(_target, payload)


def _target(arg: object) -> object:
    return arg


WRAPPERS: list[Callable[[object], object]] = [_deque, _proxy, _chain, _partial]


@pytest.fixture
def renderer() -> ValueRenderer:
    return ValueRenderer()


@pytest.mark.parametrize("wrap", WRAPPERS)
def test_a_wrapped_dataclass_keeps_its_field_redaction(
    renderer: ValueRenderer, wrap: Callable[[object], object]
) -> None:
    value = wrap(_card())

    flat = renderer.render(value)
    structured = repr(renderer.render_structured(value))

    assert SECRET not in flat
    assert "[REDACTED]" in flat
    assert SECRET not in structured
    assert "[REDACTED]" in structured


def test_a_namespace_redacts_a_deny_listed_attribute_by_name(renderer: ValueRenderer) -> None:
    value = types.SimpleNamespace(password=SECRET)

    flat = renderer.render(value)
    structured = repr(renderer.render_structured(value))

    assert SECRET not in flat
    assert "[REDACTED]" in flat
    assert SECRET not in structured
    assert "[REDACTED]" in structured


@pytest.mark.parametrize("wrap", [*WRAPPERS, lambda p: types.SimpleNamespace(item=p)])
def test_a_wrapped_value_never_has_its_own_repr_called(
    renderer: ValueRenderer, wrap: Callable[[object], object]
) -> None:
    value = wrap(SpyRepr())
    SpyRepr.calls = 0

    renderer.render(value)
    renderer.render_structured(value)

    assert SpyRepr.calls == 0
