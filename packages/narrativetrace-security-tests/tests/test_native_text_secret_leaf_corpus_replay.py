# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Corpus replay for the ``native-text-secret-leaf`` row: a secret in a leaf's own text, with no
field name or annotation for the name deny-list to match. Mirrors Java's
``NativeTextSecretLeafCorpusReplayTest``.

INTENT: the generic corpus replay proves the row builds; this proves the property the row exists
for, one element at a time so a failure names the leaf. Every one of the five must come out as the
marker on the flat path and on the structured path, the pair the routing parity replay holds
together everywhere else.
"""

from __future__ import annotations

import hostile_graphs
import pytest
from hostile_corpus import graphs

from narrativetrace.rendering import ValueRenderer
from narrativetrace.values import StringVal

_ROW_ID = "native-text-secret-leaf"
_MARKER = "[REDACTED]"
_LEAF_COUNT = 5


def _leaves() -> list[object]:
    matches = [c for c in graphs() if c.id == _ROW_ID]
    assert matches, f"{_ROW_ID} must be in graphs.json"
    built = hostile_graphs.build(matches[0], "sentinel-native-text")
    assert isinstance(built, list)
    return built


_INDEXES = list(range(_LEAF_COUNT))


def test_the_row_holds_five_leaves() -> None:
    assert len(_leaves()) == _LEAF_COUNT


@pytest.mark.parametrize("index", _INDEXES)
def test_every_leaf_renders_the_marker_on_the_flat_path(index: int) -> None:
    leaf = _leaves()[index]

    assert ValueRenderer().render(leaf) == _MARKER, type(leaf).__name__


@pytest.mark.parametrize("index", _INDEXES)
def test_every_leaf_renders_the_marker_on_the_structured_path(index: int) -> None:
    leaf = _leaves()[index]

    assert ValueRenderer().render_structured(leaf) == StringVal(_MARKER), type(leaf).__name__


def test_the_secret_text_reaches_neither_path_when_the_five_sit_in_one_list() -> None:
    renderer = ValueRenderer()
    leaves = _leaves()

    flat = renderer.render(leaves)
    structured = repr(renderer.render_structured(leaves))

    for text in (flat, structured):
        assert hostile_graphs.JWT_SHAPE not in text
        assert hostile_graphs.CARD_SHAPE not in text
