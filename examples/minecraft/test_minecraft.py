# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the naming tour: both worlds run, share a shape, and score apart on clarity."""

from __future__ import annotations

import io

import pytest
from narrativetrace_clarity import analyze

from examples.minecraft.minecraft import (
    capture_refactored,
    capture_unrefactored,
    run_example,
    scenarios,
)
from examples.tour import Scenario
from narrativetrace import ContextVarNarrativeContext, TraceTree
from narrativetrace.nodes import TraceNode


def _shape(nodes: list[TraceNode]) -> list[int]:
    return [len(n.children) for n in nodes] + [c for n in nodes for c in _shape(n.children)]


def _classes(tree: TraceTree) -> set[str]:
    def walk(nodes: list[TraceNode]) -> set[str]:
        found: set[str] = set()
        for node in nodes:
            found.add(node.signature.class_name)
            found |= walk(node.children)
        return found

    return walk(tree.roots)


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: str(s.title))
def test_every_scenario_carries_a_wiring_note_and_runs(scenario: Scenario) -> None:
    assert scenario.wiring.startswith("Wiring: ")
    assert not scenario.run(ContextVarNarrativeContext()).is_empty


def test_both_worlds_have_the_same_call_shape() -> None:
    refactored = capture_refactored(ContextVarNarrativeContext())
    unrefactored = capture_unrefactored(ContextVarNarrativeContext())
    assert _shape(refactored.roots) == _shape(unrefactored.roots)
    assert len(refactored.roots[0].children) == 6


def test_each_world_traces_five_collaborators() -> None:
    assert _classes(capture_refactored(ContextVarNarrativeContext())) == {
        "WorldServer",
        "WorldGenerator",
        "PlayerInventory",
        "CraftingTable",
        "CreatureSpawner",
    }
    assert _classes(capture_unrefactored(ContextVarNarrativeContext())) == {
        "GameManager",
        "DataProcessor",
        "StateManager",
        "ThingFactory",
        "EntityHandler",
    }


def test_domain_names_score_higher_clarity() -> None:
    refactored = analyze(capture_refactored(ContextVarNarrativeContext())).overall_score
    unrefactored = analyze(capture_unrefactored(ContextVarNarrativeContext())).overall_score
    assert refactored > unrefactored


def test_run_example_prints_both_worlds_then_the_clarity_comparison() -> None:
    out = io.StringIO()
    run_example(out)
    text = out.getvalue()
    headers = [line for line in text.splitlines() if line.startswith("=== ")]
    assert headers == [f"=== {s.title} ===" for s in scenarios()]
    assert "--- PlantUML ---" in text
    assert "^ Same call graph. Same return values. Only names differ." in text
    assert text.index("--- Clarity ---") > text.index(headers[-1])
    assert "  refactored   " in text
    assert "  unrefactored " in text
