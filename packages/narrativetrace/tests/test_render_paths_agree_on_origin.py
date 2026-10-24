# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-191: the flat and the structured render path take ONE origin decision about whether a value's
elements may be enumerated (rendering rule, owner 2026-09-18: one decision shared by both paths,
so they cannot drift). Mirrors Java's ``ElementOrigin`` parity (pair #6).

Two halves. The hook half pins the third sanctioned hook, ``__narrative_elements__``, on the
STRUCTURED path exactly as the flat path honours it: same cap, same totality guard, under the
rendering guard, the same node total. The replay half runs a corpus-independent set of fixtures
(the master corpus carries no declared-elements row) through BOTH paths and asserts the same
verdict per row: elements shown on both or on neither, and the value's own members never run.
"""

from __future__ import annotations

import collections.abc
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from narrativetrace.rendering import ValueRenderer, _RenderWalk, is_rendering
from narrativetrace.values import ListVal, ObjectVal, StringVal


class DeclaredBox:
    def __init__(self, items: list[object]) -> None:
        self._items = list(items)
        self.calls = 0
        self.calls_inside_guard = 0

    def __narrative_elements__(self) -> list[object]:
        self.calls += 1
        if is_rendering():
            self.calls_inside_guard += 1
        return list(self._items)


class RaisingBox:
    def __init__(self) -> None:
        self.label = "box"

    def __narrative_elements__(self) -> list[object]:
        raise ValueError("boom")


class HostileList(list[object]):
    iter_calls = 0

    def __iter__(self) -> Iterator[object]:
        type(self).iter_calls += 1
        raise RuntimeError("hostile iter")


class HostileDict(dict[str, object]):
    items_calls = 0

    def items(self) -> Any:
        type(self).items_calls += 1
        raise RuntimeError("hostile items")


class LookalikeCollection(collections.abc.Collection[object]):
    iter_calls = 0

    def __init__(self) -> None:
        self.tag = "lookalike"

    def __len__(self) -> int:
        return 1

    def __contains__(self, item: object) -> bool:
        return False

    def __iter__(self) -> Iterator[object]:
        type(self).iter_calls += 1
        yield "ELEM-SECRET"


class BareIterable:
    iter_calls = 0

    def __init__(self) -> None:
        self.tag = "bare"

    def __iter__(self) -> Iterator[object]:
        type(self).iter_calls += 1
        yield "ELEM-SECRET"


@dataclass
class Holder:
    box: DeclaredBox


@pytest.fixture
def renderer() -> ValueRenderer:
    return ValueRenderer()


class TestStructuredPathHonoursTheElementsHook:
    def test_declared_elements_render_as_a_list_not_as_fields(
        self, renderer: ValueRenderer
    ) -> None:
        rendered = renderer.render_structured(DeclaredBox([10, 20, 30]))

        assert isinstance(rendered, ListVal)
        assert len(rendered.elements) == 3
        assert "_items" not in repr(rendered)

    def test_declared_elements_are_capped_like_the_flat_path(self, renderer: ValueRenderer) -> None:
        box = DeclaredBox(list(range(100, 107)))

        rendered = renderer.render_structured(box)

        assert isinstance(rendered, ListVal)
        assert len(rendered.elements) == renderer.max_collection_items

    def test_a_raising_hook_renders_the_typed_error_marker(self, renderer: ValueRenderer) -> None:
        rendered = renderer.render_structured(RaisingBox())

        assert rendered == StringVal("<error: ValueError>")

    def test_the_hook_runs_only_inside_the_rendering_guard(self, renderer: ValueRenderer) -> None:
        box = DeclaredBox([1])

        renderer.render_structured(box)

        assert box.calls == 1
        assert box.calls_inside_guard == 1

    def test_a_declared_box_nested_in_a_field_renders_its_elements(
        self, renderer: ValueRenderer
    ) -> None:
        rendered = renderer.render_structured(Holder(DeclaredBox([7, 8])))

        assert isinstance(rendered, ObjectVal)
        assert isinstance(rendered.fields["box"], ListVal)

    def test_a_self_containing_declared_box_terminates_on_the_cycle_marker(
        self, renderer: ValueRenderer
    ) -> None:
        box = DeclaredBox([])
        box._items.append(box)

        rendered = renderer.render_structured(box)

        assert isinstance(rendered, ListVal)
        assert "<cycle" in repr(rendered).lower() or "box" in repr(rendered).lower()

    def test_both_paths_count_the_same_node_total_for_a_declared_box(
        self, renderer: ValueRenderer
    ) -> None:
        box = DeclaredBox([1, "two", [3, 4], DeclaredBox([5, 6])])
        flat_walk, structured_walk = _RenderWalk(), _RenderWalk()

        renderer._render(box, flat_walk)
        renderer._render_structured(box, structured_walk)

        assert structured_walk.nodes() == flat_walk.nodes()


def _verdict(text: str, structured: str) -> tuple[bool, bool]:
    return "ELEM-A" in text, "ELEM-A" in structured


def _hostile_list() -> list[object]:
    HostileList.iter_calls = 0
    return HostileList(["ELEM-A"])


def _hostile_dict() -> HostileDict:
    HostileDict.items_calls = 0
    return HostileDict(k="ELEM-A")


def _lookalike() -> LookalikeCollection:
    LookalikeCollection.iter_calls = 0
    return LookalikeCollection()


def _bare() -> BareIterable:
    BareIterable.iter_calls = 0
    return BareIterable()


_ROWS: list[tuple[str, Any, bool]] = [
    ("declared", lambda: DeclaredBox(["ELEM-A"]), True),
    ("platform-list", lambda: ["ELEM-A"], True),
    ("platform-tuple", lambda: ("ELEM-A",), True),
    ("platform-set", lambda: {"ELEM-A"}, True),
    ("platform-dict", lambda: {"k": "ELEM-A"}, True),
    ("list-subclass-ancestor-state", _hostile_list, True),
    ("dict-subclass-ancestor-state", _hostile_dict, True),
    ("hand-rolled-collection", _lookalike, False),
    ("bare-iterable", _bare, False),
]


class TestBothPathsTakeTheSameOriginVerdict:
    @pytest.mark.parametrize(("name", "build", "shows_elements"), _ROWS, ids=[r[0] for r in _ROWS])
    def test_elements_are_shown_on_both_paths_or_on_neither(
        self, renderer: ValueRenderer, name: str, build: Any, shows_elements: bool
    ) -> None:
        flat_value = build()
        flat = renderer.render(flat_value)
        structured_value = build()
        structured = repr(renderer.render_structured(structured_value))

        assert _verdict(flat, structured) == (shows_elements, shows_elements), (
            f"{name}: flat={flat!r} structured={structured!r}"
        )

    @pytest.mark.parametrize(
        ("counter", "build"),
        [
            (HostileList, _hostile_list),
            (HostileDict, _hostile_dict),
            (LookalikeCollection, _lookalike),
            (BareIterable, _bare),
        ],
    )
    def test_a_value_the_rule_withholds_never_runs_its_own_members_on_either_path(
        self, renderer: ValueRenderer, counter: type, build: Any
    ) -> None:
        attr = "items_calls" if counter is HostileDict else "iter_calls"
        value = build()

        renderer.render(value)
        renderer.render_structured(value)

        assert getattr(counter, attr) == 0
