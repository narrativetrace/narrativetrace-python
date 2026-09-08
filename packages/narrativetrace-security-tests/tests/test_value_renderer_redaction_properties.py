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
from oracles import contains_nowhere, idempotent, no_new_threads, sentinel_token, within_budget

from narrativetrace.rendering import ValueRenderer


def _flat(renderer: ValueRenderer, graph: object) -> str:
    return within_budget("flat render", lambda: renderer.render(graph))


def _structured(renderer: ValueRenderer, graph: object) -> str:
    return within_budget("structured render", lambda: repr(renderer.render_structured(graph)))


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
