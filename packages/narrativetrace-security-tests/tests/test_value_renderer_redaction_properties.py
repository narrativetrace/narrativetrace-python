# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A, target 2: the value renderer over hostile object graphs.

``ValueRendererRedactionPropertyTest`` -- the primary redaction oracle: plant a fresh
token behind ``@not_traced``/a deny-listed name anywhere in an arbitrary graph, render it on both
paths, and assert the token is in neither output, whole or by prefix.
"""

from __future__ import annotations

import pytest
from fuzz_config import fuzz_settings
from hostile_corpus import GraphCase, graphs
from hostile_graphs import _LAYER_BUILDERS, SecretRecord, _apply_layers, build
from hypothesis import given
from hypothesis import strategies as st
from oracles import contains_nowhere, idempotent, no_new_threads, sentinel_token

from narrativetrace.rendering import ValueRenderer


def _flat(renderer: ValueRenderer, graph: object) -> str:
    return renderer.render(graph)


def _structured(renderer: ValueRenderer, graph: object) -> str:
    return repr(renderer.render_structured(graph))


def _outputs(renderer: ValueRenderer, graph: object) -> dict[str, str]:
    return {"flat": _flat(renderer, graph), "structured": _structured(renderer, graph)}


class TestCorpusGraphs:
    @pytest.mark.parametrize("case", graphs(), ids=str)
    def test_every_hostile_graph_renders_without_crashing(self, case: GraphCase) -> None:
        sentinel = sentinel_token()
        graph = build(case, sentinel)
        renderer = ValueRenderer()
        outputs = no_new_threads(lambda: _outputs(renderer, graph))
        if case.carries_secret:
            contains_nowhere(sentinel, outputs)

    @pytest.mark.parametrize("case", [c for c in graphs() if c.carries_secret], ids=str)
    def test_rendering_a_secret_graph_is_idempotent(self, case: GraphCase) -> None:
        sentinel = sentinel_token()
        graph = build(case, sentinel)
        renderer = ValueRenderer()
        idempotent(lambda: renderer.render(graph))


_MAX_SANE_FLAT_LENGTH = 4_000
"""A generous, deterministic ceiling for :meth:`ValueRenderer.render` over any corpus graph:
comfortably above every legitimately-capped shape measured today (the deepest chains and widest
containers reach roughly a thousand characters), and orders of magnitude below what
``huge-to-string`` alone would produce (1,048,576 characters) the moment its string cap broke."""

_MAX_SANE_STRUCTURED_LENGTH = 8_000
"""Same reasoning as :data:`_MAX_SANE_FLAT_LENGTH`, sized for the structured channel's ``repr``
overhead (measured up to ~2,800 characters for the widest legitimate corpus shape today)."""


class TestBoundedWork:
    """Replaces a removed wall-clock hang detector (family release rule 3, 2026-09-07: wall-clock,
    GC and scheduler are never test inputs -- ``oracles.within_budget`` used to wrap both render
    calls here) with the deterministic property the timing bound stood in for: ``ValueRenderer``'s
    string/collection/object/depth caps bound every hostile graph's rendered size to a small,
    generous ceiling regardless of the graph's own size -- exactly as sensitive to a caps
    regression as the removed timing bound was, without depending on host load to hold."""

    @pytest.mark.parametrize("case", graphs(), ids=str)
    def test_every_hostile_graph_renders_with_bounded_output(self, case: GraphCase) -> None:
        graph = build(case, sentinel_token())
        outputs = _outputs(ValueRenderer(), graph)

        assert len(outputs["flat"]) <= _MAX_SANE_FLAT_LENGTH, (
            f"{case.id} produced unbounded flat output ({len(outputs['flat'])} chars)"
        )
        assert len(outputs["structured"]) <= _MAX_SANE_STRUCTURED_LENGTH, (
            f"{case.id} produced unbounded structured output ({len(outputs['structured'])} chars)"
        )

    def test_a_megabyte_to_string_is_truncated_to_the_string_cap(self) -> None:
        """The deterministic property the removed wall-clock assertion was actually guarding for
        ``huge-to-string``: a hostile ``__str__`` returning a megabyte is truncated, never
        consumed whole, in either channel."""
        case = next(c for c in graphs() if c.id == "huge-to-string")
        graph = build(case, sentinel_token())
        outputs = _outputs(ValueRenderer(), graph)

        assert outputs["flat"].endswith("…"), "a truncated value must end in the truncation marker"
        assert len(outputs["flat"]) <= _MAX_SANE_FLAT_LENGTH
        assert "…" in outputs["structured"], "the structured channel must carry the same marker"
        assert len(outputs["structured"]) <= _MAX_SANE_STRUCTURED_LENGTH


_WRAPPER_STACKS = st.lists(st.sampled_from(list(_LAYER_BUILDERS)), max_size=6)


class TestGeneratedWrapperStacks:
    @fuzz_settings
    @given(_WRAPPER_STACKS)
    def test_a_redacted_component_survives_any_stack_of_wrappers(self, layers: list[str]) -> None:
        sentinel = sentinel_token()
        graph = _apply_layers(tuple(layers), SecretRecord("item", sentinel))
        rendered = ValueRenderer().render(graph)
        assert sentinel not in rendered

    @fuzz_settings
    @given(_WRAPPER_STACKS)
    def test_the_structured_path_redacts_wherever_the_flat_path_does(
        self, layers: list[str]
    ) -> None:
        sentinel = sentinel_token()
        graph = _apply_layers(tuple(layers), SecretRecord("item", sentinel))
        rendered = repr(ValueRenderer().render_structured(graph))
        assert sentinel not in rendered

    @fuzz_settings
    @given(st.integers(min_value=1, max_value=200))
    def test_a_redacted_component_survives_an_arbitrarily_deep_chain(self, depth: int) -> None:
        sentinel = sentinel_token()
        graph = _apply_layers(("holder",) * depth, SecretRecord("item", sentinel))
        assert sentinel not in ValueRenderer().render(graph)

    @fuzz_settings
    @given(st.integers(min_value=0, max_value=500), st.sampled_from(["list", "map"]))
    def test_a_redacted_component_survives_an_arbitrarily_wide_container(
        self, width: int, container: str
    ) -> None:
        sentinel = sentinel_token()
        payload = SecretRecord("item", sentinel)
        filler = width - 1 if width > 0 else 0
        graph: object
        if container == "map":
            mapping: dict[str, object] = {f"k{i}": None for i in range(filler)}
            mapping[f"k{filler}"] = payload
            graph = mapping
        else:
            graph = [None] * filler + [payload]
        assert sentinel not in ValueRenderer().render(graph)
