# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Writer-driven identity conformance: the bytes on disk carry one trace id, and it is valid.

Prerequisite 8 of the Java conformance plan says the check must run against what a real writer put
on disk, not against an in-memory dict. Two captures are covered because they reach identity by
different rungs of the ladder: a **plain capture** through the real context inherits the span
context it created, while a **hand-built context-free tree** — the shape a unit test produces —
has nothing to inherit and is given a generated id.

The chapter has no on-disk writer here (the pytest plugin writes the tree document and the
canonical array), so the chapter case writes the real exporter's bytes itself and reads them back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conformance import (
    CHAPTER_SCHEMA,
    CHAPTER_TREE_SCHEMA,
    ENTRY_SCHEMA,
    validate_against,
    validate_json_text,
)

from narrativetrace.chapter import export_chapter
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.output.writer import TraceArtifact, write_trace
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.trace_object import trace_object
from narrativetrace.tree import TraceTree

MS = 1_000_000
METADATA = TraceMetadata("Customer places order", ScenarioResult.SUCCESS)


class OrderService:
    def place_order(self, sku: str) -> str:
        return f"ordered {sku}"


def _captured_tree() -> TraceTree:
    """A real capture: the context creates the span, so identity is inherited, not generated."""
    context = ContextVarNarrativeContext()
    trace_object(OrderService(), context).place_order("sku-1")
    return context.capture_trace()


def _hand_built_tree() -> TraceTree:
    """The shape a plain unit test produces: no span context anywhere, so the id is generated."""
    node = TraceNode(
        signature=MethodSignature("OrderService", "place_order", []),
        children=[],
        outcome=Returned('"ordered sku-1"'),
        duration_nanos=7 * MS,
    )
    return TraceTree([node])


@pytest.fixture(params=[_captured_tree, _hand_built_tree], ids=["captured", "hand-built"])
def tree(request: pytest.FixtureRequest) -> TraceTree:
    built: TraceTree = request.param()
    return built


def _write_artifacts(tree: TraceTree, base_dir: Path) -> tuple[Path, Path]:
    """Writes the canonical array through the real writer and the chapter beside it."""
    result = write_trace(
        tree,
        METADATA,
        TraceArtifact(base_dir, "OrderService", "place_order", canonical=True),
    )
    canonical = base_dir / "traces" / "OrderService" / "place_order.canonical.json"
    assert canonical in result.files, f"the writer produced no canonical artifact at {canonical}"
    chapter = base_dir / "traces" / "OrderService" / "place_order.chapter.json"
    chapter.write_text(export_chapter(tree, METADATA), encoding="utf-8")
    return chapter, canonical


def _read_entries(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return entries


def test_the_canonical_bytes_on_disk_satisfy_the_entry_schema(
    tree: TraceTree, tmp_path: Path
) -> None:
    _, canonical = _write_artifacts(tree, tmp_path)

    entries = _read_entries(canonical)

    assert [entry["nt.eventType"] for entry in entries] == ["method_enter", "method_exit"]
    for entry in entries:
        validate_against(entry, ENTRY_SCHEMA)


def test_the_chapter_bytes_on_disk_satisfy_the_chapter_schema(
    tree: TraceTree, tmp_path: Path
) -> None:
    chapter, _ = _write_artifacts(tree, tmp_path)

    document = validate_json_text(chapter.read_text(encoding="utf-8"), CHAPTER_SCHEMA)

    validate_json_text(document["nt.chapterTree"], CHAPTER_TREE_SCHEMA)


def test_the_chapter_and_its_canonical_entries_name_the_same_trace(
    tree: TraceTree, tmp_path: Path
) -> None:
    """The whole point of resolving identity on the tree: two writers, one trace."""
    chapter, canonical = _write_artifacts(tree, tmp_path)

    document = json.loads(chapter.read_text(encoding="utf-8"))
    entries = _read_entries(canonical)

    assert {entry["trace_id"] for entry in entries} == {document["trace_id"]}
    assert {entry["nt.traceName"] for entry in entries} == {document["nt.traceName"]}
    assert {entry["nt.storyId"] for entry in entries} == {document["nt.storyId"]}


def test_the_chapter_and_the_tree_embedded_in_it_name_the_same_trace(
    tree: TraceTree, tmp_path: Path
) -> None:
    """26c, third emitter: `nt.chapterTree`'s own `trace` block must not name a different trace
    than the chapter embedding it — span-less (hand-built) included."""
    chapter, _ = _write_artifacts(tree, tmp_path)

    document = json.loads(chapter.read_text(encoding="utf-8"))
    embedded = json.loads(document["nt.chapterTree"])

    assert embedded["trace"]["traceId"] == document["trace_id"]
    assert embedded["trace"]["traceName"] == document["nt.traceName"]


def test_the_embedded_tree_of_a_span_less_capture_still_validates_on_disk(tmp_path: Path) -> None:
    chapter, _ = _write_artifacts(_hand_built_tree(), tmp_path)

    document = json.loads(chapter.read_text(encoding="utf-8"))
    embedded = validate_json_text(document["nt.chapterTree"], CHAPTER_TREE_SCHEMA)

    assert embedded["trace"]["traceId"] == document["trace_id"]


def test_the_embedded_tree_finds_the_trace_on_a_deeper_node_when_no_root_carries_one(
    tmp_path: Path,
) -> None:
    """Roots-only scanning was the other half of the divergence: a mixed tree whose context sits
    on a child resolved to "no trace at all" here while the chapter and canonical entries, both
    depth-first, inherited it."""
    child = TraceNode(
        signature=MethodSignature("PaymentService", "charge", []),
        children=[],
        outcome=Returned('"TXN-1"'),
        duration_nanos=2 * MS,
        span_context=SpanContext(
            trace_id=TraceId("b" * 32), span_id=SpanId("c" * 16), service_name="order-service"
        ),
    )
    root = TraceNode(
        signature=MethodSignature("OrderService", "place_order", []),
        children=[child],
        outcome=Returned('"order-1"'),
        duration_nanos=4 * MS,
    )
    mixed_tree = TraceTree([root])

    chapter, _ = _write_artifacts(mixed_tree, tmp_path)
    document = json.loads(chapter.read_text(encoding="utf-8"))
    embedded = json.loads(document["nt.chapterTree"])

    assert embedded["trace"]["traceId"] == document["trace_id"] == "b" * 32
    assert embedded["trace"]["serviceName"] == "order-service"


def _first_entry(tree: TraceTree, base_dir: Path) -> dict[str, Any]:
    _, canonical = _write_artifacts(tree, base_dir)
    return _read_entries(canonical)[0]


def test_two_context_free_runs_are_told_apart_on_disk(tmp_path: Path) -> None:
    """Byte-identical artifacts for two unrelated runs would defeat `trace_id`'s only job — which
    is why the synthetic constant was retired. The derived story stays stable across both."""
    first = _first_entry(_hand_built_tree(), tmp_path / "first")
    second = _first_entry(_hand_built_tree(), tmp_path / "second")

    assert first["trace_id"] != second["trace_id"]
    assert first["nt.storyId"] == second["nt.storyId"] == "OrderService.place_order"
