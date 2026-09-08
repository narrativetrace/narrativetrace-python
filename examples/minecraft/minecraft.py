# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Naming tour: how much naming alone changes trace quality.

Two modules perform comparable "player joins world" work with five collaborators each:

- :mod:`examples.minecraft.refactored` — domain-rich names: ``WorldGenerator``,
  ``PlayerInventory``, ``CraftingTable``, ``CreatureSpawner``, ``WorldServer``.
- :mod:`examples.minecraft.unrefactored` — the same intent hidden behind generic labels:
  ``DataProcessor``, ``StateManager``, ``ThingFactory``, ``EntityHandler``, ``GameManager``.

Both run back to back, wired byte for byte the same way, so the traces can be compared side by
side; the clarity scores at the end put a number on the difference. A teaching aid about naming
and observability, not a gameplay sample. Run it::

    python -m examples.minecraft
    python -m examples.demo --example minecraft
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from narrativetrace_clarity import analyze

from examples.minecraft import refactored, unrefactored
from examples.tour import MERMAID, PLANTUML, TREE, Scenario, narrated_run, walk
from narrativetrace import NarrativeContext, TraceTree, trace_object

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO


def capture_refactored(context: NarrativeContext) -> TraceTree:
    """Trace of the domain-named world."""
    server = trace_object(
        refactored.WorldServer(
            trace_object(refactored.WorldGenerator(), context),
            trace_object(refactored.PlayerInventory(), context),
            trace_object(refactored.CraftingTable(), context),
            trace_object(refactored.CreatureSpawner(), context),
        ),
        context,
    )
    server.player_joined("Steve")
    return context.capture_trace()


def capture_unrefactored(context: NarrativeContext) -> TraceTree:
    """Trace of the generic-named world (identical structure)."""
    manager = trace_object(
        unrefactored.GameManager(
            trace_object(unrefactored.DataProcessor(), context),
            trace_object(unrefactored.StateManager(), context),
            trace_object(unrefactored.ThingFactory(), context),
            trace_object(unrefactored.EntityHandler(), context),
        ),
        context,
    )
    manager.handle("Steve")
    return context.capture_trace()


def scenarios() -> list[Scenario]:
    """The two worlds, refactored first."""
    return [
        Scenario(
            "Refactored: Player Joins World",
            "Wiring: no container, no decorators — every collaborator is wrapped with "
            "trace_object(service, context) and handed to WorldServer, so the trace is the "
            "call graph the code already has.",
            capture_refactored,
            sections=(TREE, MERMAID, PLANTUML),
            intro=("Domain-specific names make the trace self-documenting.",),
        ),
        Scenario(
            "Unrefactored: Player Joins World",
            "Wiring: byte for byte the setup above — same wrappers, same context after a "
            "reset(). Only the class and method names differ, and that is the whole point.",
            capture_unrefactored,
            sections=(TREE,),
            intro=("Generic names — same behavior, but the trace tells you nothing.",),
            notice=(
                "^ Same call graph. Same return values. Only names differ.",
                "If your code can't tell its own story, it needs refactoring.",
            ),
        ),
    ]


def print_clarity_comparison(captured: Sequence[tuple[Scenario, TraceTree]], out: TextIO) -> None:
    """Scores both trees so the naming difference gets a number."""
    out.write("\n--- Clarity ---\n\n")
    for scenario, tree in captured:
        label = scenario.title.split(":")[0].lower()
        out.write(f"  {label:<12} {analyze(tree).overall_score:.2f}\n")


def run_example(out: TextIO, *, classic: bool = False) -> None:
    """Walks both worlds, then prints their clarity scores side by side."""
    with narrated_run(out, classic=classic) as context:
        print_clarity_comparison(walk(scenarios(), out, context), out)


def main(argv: Sequence[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else list(argv)
    run_example(sys.stdout, classic="--classic" in args)


if __name__ == "__main__":
    main()
