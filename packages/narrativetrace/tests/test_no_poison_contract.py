# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Covers the same totality invariant as Java's ``NoPoisonContractTest`` (a 2026-09-01 finding):
every trace boundary that runs on the application thread must be total.

Value rendering must never let a hostile value's ``toString``/iteration/state-probe equivalents
escape into the host. This module pins the ``ValueRenderer`` half of the contract;
``test_trace_object.py`` and other modules pin the entry/exit/pipeline halves.
"""

from __future__ import annotations

import concurrent.futures
from enum import Enum
from typing import Any

from narrativetrace.rendering import ValueRenderer
from narrativetrace.values import ListVal, ObjectVal, StringVal


class _ThrowingIterator(list[object]):
    def __iter__(self) -> Any:
        raise AssertionError("iterator must not be touched by tracing")


class _ThrowingNumber(int):
    def __str__(self) -> str:
        raise AssertionError("number toString must not be touched by tracing")


class _ThrowingEnum(Enum):
    OK = "ok"

    def __str__(self) -> str:
        raise AssertionError("enum toString must not be touched by tracing")


class _ThrowingDict(dict[str, object]):
    def items(self) -> Any:
        raise AssertionError("map entrySet must not be touched by tracing")


class _ThrowingDoneFuture(concurrent.futures.Future[object]):
    def done(self) -> bool:
        raise AssertionError("future isDone must not be touched by tracing")


class _ThrowingCancelledFuture(concurrent.futures.Future[object]):
    def __init__(self) -> None:
        super().__init__()
        self.set_result("value")

    def cancelled(self) -> bool:
        raise AssertionError("future isCancelled must not be touched by tracing")


class _ExoticFailure:
    """A failure point not anticipated by any locally-guarded branch: its ``__dict__`` itself
    raises on access, defeating the introspection path from the inside rather than through one
    of the specific hostile methods (``__str__``/``__iter__``/etc.) the other fixtures target.
    """

    @property
    def __dict__(self) -> dict[str, object]:  # type: ignore[override]
        raise AssertionError("nothing about this object may be touched")


class TestCollectionTotality:
    def test_flat_render_survives_a_throwing_iterator(self) -> None:
        rendered = ValueRenderer().render(_ThrowingIterator([1, 2]))
        assert "_ThrowingIterator" in rendered

    def test_structured_render_survives_a_throwing_iterator(self) -> None:
        rendered = ValueRenderer().render_structured(_ThrowingIterator([1, 2]))
        assert rendered == StringVal("<_ThrowingIterator>")

    def test_one_bad_element_does_not_poison_a_sibling_list(self) -> None:
        rendered = ValueRenderer().render([_ThrowingIterator([1]), "ok"])
        assert '"ok"' in rendered
        assert "_ThrowingIterator" in rendered


class TestMapTotality:
    def test_flat_render_survives_a_throwing_items(self) -> None:
        rendered = ValueRenderer().render(_ThrowingDict({"a": 1}))
        assert "_ThrowingDict" in rendered

    def test_structured_render_survives_a_throwing_items(self) -> None:
        rendered = ValueRenderer().render_structured(_ThrowingDict({"a": 1}))
        assert rendered == StringVal("<_ThrowingDict>")


class TestNumberTotality:
    def test_flat_render_survives_a_throwing_number_str(self) -> None:
        rendered = ValueRenderer().render(_ThrowingNumber(5))
        assert rendered == "<error: AssertionError>"


class TestEnumTotality:
    def test_flat_render_survives_a_throwing_enum_str(self) -> None:
        rendered = ValueRenderer().render(_ThrowingEnum.OK)
        assert rendered == "<error: AssertionError>"

    def test_structured_render_survives_a_throwing_enum_str(self) -> None:
        rendered = ValueRenderer().render_structured(_ThrowingEnum.OK)
        assert rendered == StringVal("<error: AssertionError>")


class TestFutureTotality:
    def test_flat_render_survives_a_throwing_done(self) -> None:
        rendered = ValueRenderer().render(_ThrowingDoneFuture())
        assert rendered == "<failed>"

    def test_structured_render_survives_a_throwing_done(self) -> None:
        rendered = ValueRenderer().render_structured(_ThrowingDoneFuture())
        assert rendered == StringVal("<failed>")

    def test_flat_render_survives_a_throwing_cancelled_after_done(self) -> None:
        rendered = ValueRenderer().render(_ThrowingCancelledFuture())
        assert rendered == "<failed>"


class TestPerElementIsolation:
    """An element whose failure is not one of the locally-guarded shapes above must still be
    isolated to itself: a healthy sibling in the same list/dict must render normally rather than
    the whole container collapsing to a single ``<TypeName>`` marker.
    """

    def test_flat_list_with_one_exotic_element_still_renders_its_sibling(self) -> None:
        rendered = ValueRenderer().render([_ExoticFailure(), "ok"])
        assert '"ok"' in rendered
        assert "_ExoticFailure" in rendered

    def test_structured_list_with_one_exotic_element_still_renders_its_sibling(self) -> None:
        rendered = ValueRenderer().render_structured([_ExoticFailure(), "ok"])
        assert isinstance(rendered, ListVal)
        assert StringVal("ok") in rendered.elements

    def test_flat_map_with_one_exotic_value_still_renders_its_sibling(self) -> None:
        rendered = ValueRenderer().render({"bad": _ExoticFailure(), "good": "ok"})
        assert '"ok"' in rendered
        assert "_ExoticFailure" in rendered

    def test_flat_map_with_a_throwing_key_still_renders_its_sibling(self) -> None:
        class _ThrowingKey:
            def __str__(self) -> str:
                raise AssertionError("key toString must not be touched by tracing")

        rendered = ValueRenderer().render({_ThrowingKey(): "bad", "good": "ok"})
        assert '"ok"' in rendered


class TestRendererTotalOuterBoundary:
    """Even an unanticipated failure point must not escape ``render``/``render_structured`` when
    it is the outermost value passed in, not nested inside a healthy container.
    """

    def test_flat_render_never_raises(self) -> None:
        rendered = ValueRenderer().render(_ExoticFailure())
        assert isinstance(rendered, str)

    def test_structured_render_never_raises(self) -> None:
        rendered = ValueRenderer().render_structured(_ExoticFailure())
        assert isinstance(rendered, (ObjectVal, StringVal, ListVal))
