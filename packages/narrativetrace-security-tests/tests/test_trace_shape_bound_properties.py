# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A: a deep or cyclic ``TraceNode`` tree must not crash or hang any renderer or exporter --
``narrativetrace.tree_walk.TreeWalk`` is the shared bound every one of them now goes through.

``TraceShapeBoundPropertyTest``. Companion to ``test_output_format_properties.py``
(target 3 of the parity document's fuzzing list), scoped to the tree-shape corpus rather than the
value corpus: those ``hostile_corpus.strings`` cases exercise a hostile *value* inside an
otherwise ordinary one-node tree, this one exercises a hostile *tree structure* around an ordinary
value.
"""

from __future__ import annotations

import json

import pytest
from conformance import (
    CHAPTER_SCHEMA,
    CHAPTER_TREE_SCHEMA,
    ENTRY_SCHEMA,
    validate_against,
    validate_json_text,
)
from emitters import every_output, metadata_for
from hostile_corpus import TraceShapeCase, trace_shapes
from oracles import bounded_size, no_new_threads
from trace_shapes import build

from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import CYCLE_MARKER

_METADATA = metadata_for("trace shape scenario")


def _outputs(case: TraceShapeCase) -> dict[str, str]:
    tree = build(case)
    return no_new_threads(lambda: every_output(tree, _METADATA))


class TestEveryTraceShapeIsWellFormedAndBounded:
    @pytest.mark.parametrize("case", trace_shapes(), ids=str)
    def test_every_format_stays_well_formed_and_bounded(self, case: TraceShapeCase) -> None:
        outputs = _outputs(case)
        bounded_size(outputs)
        validate_json_text(outputs["json-chapter-tree"], CHAPTER_TREE_SCHEMA)
        validate_json_text(outputs["json-chapter"], CHAPTER_SCHEMA)
        for entry in json.loads(outputs["canonical-entries"]):
            validate_against(entry, ENTRY_SCHEMA)


class TestEveryCyclicTraceShapeCarriesTheCycleMarker:
    """The cyclic shapes specifically: every renderer must say so, with the same marker text
    ``tree_walk.CYCLE_MARKER`` defines, not merely avoid crashing."""

    @pytest.mark.parametrize("case", [c for c in trace_shapes() if c.kind == "cycle"], ids=str)
    def test_every_renderer_shows_the_cycle_marker(self, case: TraceShapeCase) -> None:
        outputs = _outputs(case)
        for name in ("mermaid", "plantuml", "markdown-body", "indented-text", "prose"):
            assert CYCLE_MARKER in outputs[name], name


class TestEveryTraceShapeSurvivesEquality:
    """``TraceNode`` is a public frozen dataclass, so its generated ``__eq__`` is reachable by
    any caller -- not just renderers -- and walks ``children`` exactly like a renderer does. Two
    independently built roots of the same shape (no shared object identity, so the cheap identity
    short-circuit never fires) must compare correctly without a stack overflow, cyclic shapes
    included. Compares ``roots[0]`` rather than the whole :class:`TraceTree`: an empty-context
    tree mints a fresh random ``trace_id`` on every :func:`build` call
    (:meth:`TraceTree._resolved_trace_id`), which would make two structurally identical trees
    compare unequal for a reason that has nothing to do with the walk under test here."""

    @pytest.mark.parametrize("case", trace_shapes(), ids=str)
    def test_two_independent_copies_of_the_same_shape_compare_equal(
        self, case: TraceShapeCase
    ) -> None:
        left = build(case).roots[0]
        right = build(case).roots[0]
        assert left == right

    @pytest.mark.parametrize("case", trace_shapes(), ids=str)
    def test_a_shape_never_equals_an_empty_tree(self, case: TraceShapeCase) -> None:
        tree: TraceTree = build(case)
        assert tree != TraceTree([])
