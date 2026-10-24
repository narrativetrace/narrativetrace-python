# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Corpus replay for the two ``graphs.json`` rows that pin the origin decision's element side on
BOTH rendering paths: ``declared-elements`` (the third sanctioned hook, ``__narrative_elements__``)
and ``structured-path-user-subclass-ancestor-state`` (a user subclass of a platform ``list`` and of
a platform ``dict``, read through the ancestor's own state). Mirrors Java's
``DeclaredElementsCorpusReplayTest``.

INTENT: the generic corpus replays assert containment and well-formedness for every row. They
cannot say that the SAME elements, under the SAME cap, were shown on the flat and the structured
path, nor that the fixture's own members did or did not run. Those are the properties these rows
exist for, so they are asserted here, flat and structured side by side.

The two paths encode a cap differently on purpose (a trailing ellipsis in text against a shorter
list in the tree), so the witness is the set of element markers present, not the shape of the
rendering. The structured tree is flattened through its ``repr``, which spells out every nested
value.
"""

from __future__ import annotations

import hostile_graphs
import pytest
from hostile_corpus import GraphCase, graphs

from narrativetrace.rendering import ValueRenderer

_DECLARED_ROW = "declared-elements"
_SUBCLASS_ROW = "structured-path-user-subclass-ancestor-state"


def _row(row_id: str) -> GraphCase:
    matches = [c for c in graphs() if c.id == row_id]
    assert matches, f"no graphs.json row with id {row_id}"
    return matches[0]


def _build(row_id: str, sentinel: str) -> object:
    return hostile_graphs.build(_row(row_id), sentinel)


@pytest.fixture
def renderer() -> ValueRenderer:
    return ValueRenderer()


class TestDeclaredElementsRow:
    def test_same_elements_under_the_same_cap_on_both_paths(self, renderer: ValueRenderer) -> None:
        flat = renderer.render(_build(_DECLARED_ROW, "sentinel-declared-flat"))
        structured = repr(
            renderer.render_structured(_build(_DECLARED_ROW, "sentinel-declared-structured"))
        )

        for text in (flat, structured):
            for shown in ("elem-1", "elem-4", "entry-key-0", "entry-key-4"):
                assert shown in text
            for hidden in ("elem-5", "elem-6", "entry-key-5", "entry-key-6"):
                assert hidden not in text
            assert "sentinel-declared" not in text

    def test_a_raising_hook_renders_the_typed_error_marker_on_both_paths(
        self, renderer: ValueRenderer
    ) -> None:
        flat = renderer.render(_build(_DECLARED_ROW, "sentinel-declared-raise-flat"))
        structured = repr(
            renderer.render_structured(_build(_DECLARED_ROW, "sentinel-declared-raise-struct"))
        )

        assert "<error: RuntimeError>" in flat
        assert "<error: RuntimeError>" in structured

    @pytest.mark.parametrize("structured", [False, True], ids=["flat", "structured"])
    def test_each_hook_runs_once_and_only_under_the_rendering_guard(
        self, renderer: ValueRenderer, structured: bool
    ) -> None:
        declared = hostile_graphs.declared_elements("sentinel-hook-counts")
        _render(renderer, declared, structured)
        iterable, mapping = declared[0], declared[1]

        assert isinstance(iterable, hostile_graphs._DeclaredElementsIterable)
        assert isinstance(mapping, hostile_graphs._DeclaredElementsMap)
        assert iterable.hook_calls == 1
        assert iterable.guard_active_during_hook is True
        assert mapping.hook_calls == 1
        assert mapping.guard_active_during_hook is True


class TestUserSubclassAncestorStateRow:
    def test_ancestor_state_is_shown_on_both_paths(self, renderer: ValueRenderer) -> None:
        flat = renderer.render(_build(_SUBCLASS_ROW, "sentinel-subclass-flat"))
        structured = repr(
            renderer.render_structured(_build(_SUBCLASS_ROW, "sentinel-subclass-structured"))
        )

        for text in (flat, structured):
            assert "ancestor-list-element" in text
            assert "ancestor-map-value" in text
            assert "sentinel-subclass" not in text
            assert "<error" not in text

    @pytest.mark.parametrize("structured", [False, True], ids=["flat", "structured"])
    def test_the_overrides_never_run(self, renderer: ValueRenderer, structured: bool) -> None:
        subclasses = hostile_graphs.user_subclass_ancestor_state("sentinel-override-counts")
        _render(renderer, subclasses, structured)
        ancestor_list, ancestor_map = subclasses[0], subclasses[1]

        assert isinstance(ancestor_list, hostile_graphs._AncestorStateList)
        assert isinstance(ancestor_map, hostile_graphs._AncestorStateMap)
        assert ancestor_list.override_calls == 0
        assert ancestor_map.override_calls == 0


def _render(renderer: ValueRenderer, graph: object, structured: bool) -> None:
    if structured:
        renderer.render_structured(graph)
    else:
        renderer.render(graph)
