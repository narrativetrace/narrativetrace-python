# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for the chapter export invariants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from narrativetrace.chapter import export_chapter
from narrativetrace.export import export_document
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree
from narrativetrace.tree_canonical import entries_from_tree

TRACE = TraceId("b" * 32)
CLOCK = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
CANONICAL_ORDER = (
    "timestamp",
    "level",
    "message",
    "service",
    "trace_id",
    "nt.entryType",
    "nt.storyId",
    "nt.chapterId",
    "nt.title",
    "nt.outcome",
    "nt.completionStatus",
    "nt.traceName",
    "nt.schemaVersion",
    "nt.totalDurationMs",
    "nt.entryCount",
    "nt.chapterTree",
)
REQUIRED_ALWAYS = (
    "timestamp",
    "level",
    "message",
    "service",
    "trace_id",
    "nt.entryType",
    "nt.storyId",
    "nt.chapterId",
    "nt.title",
    "nt.outcome",
    "nt.completionStatus",
    "nt.traceName",
    "nt.schemaVersion",
    "nt.entryCount",
    "nt.chapterTree",
)
"""Every key a chapter always carries. Identity joined this list on 2026-08-30: it is generated
eagerly, so no capture — span-less or empty — can omit `trace_id`, the story, or the chapter."""


@dataclass
class _Spec:
    outcome_kind: str
    has_span: bool
    duration_nanos: int
    children: list[_Spec]


_kinds = st.sampled_from(["returned", "threw", "incomplete", "none"])
_leaf = st.builds(_Spec, _kinds, st.booleans(), st.integers(0, 10**12), st.just([]))
_spec_tree = st.recursive(
    _leaf,
    lambda children: st.builds(
        _Spec, _kinds, st.booleans(), st.integers(0, 10**12), st.lists(children, max_size=3)
    ),
    max_leaves=10,
)


def _outcome(kind: str) -> TraceOutcome | None:
    if kind == "returned":
        return Returned("v")
    if kind == "threw":
        return Threw(ValueError("boom"))
    if kind == "incomplete":
        return Incomplete()
    return None


def _node(spec: _Spec, counter: list[int]) -> TraceNode:
    counter[0] += 1
    span = (
        SpanContext(trace_id=TRACE, span_id=SpanId(format(counter[0], "016x")))
        if spec.has_span
        else None
    )
    return TraceNode(
        signature=MethodSignature("C", f"m{counter[0]}", []),
        children=[_node(child, counter) for child in spec.children],
        outcome=_outcome(spec.outcome_kind),
        duration_nanos=spec.duration_nanos,
        span_context=span,
    )


def _tree(specs: list[_Spec]) -> TraceTree:
    counter = [0]
    return TraceTree([_node(spec, counter) for spec in specs])


def _count(nodes: list[TraceNode]) -> int:
    return sum(1 + _count(node.children) for node in nodes)


def _chapter(tree: TraceTree) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(
        export_chapter(tree, TraceMetadata("s", ScenarioResult.SUCCESS), clock=lambda: CLOCK)
    )
    return doc


@given(st.lists(_spec_tree, max_size=4))
def test_export_is_always_parseable_json_with_the_required_fields(specs: list[_Spec]) -> None:
    doc = _chapter(_tree(specs))
    for key in REQUIRED_ALWAYS:
        assert key in doc
    assert doc["nt.entryType"] == "chapter"
    assert doc["nt.outcome"] in {"success", "failure", "partial"}
    assert doc["level"] in {"info", "error"}


@given(st.lists(_spec_tree, max_size=4))
def test_entry_count_equals_the_number_of_nodes_in_the_tree(specs: list[_Spec]) -> None:
    tree = _tree(specs)
    assert _chapter(tree)["nt.entryCount"] == _count(tree.roots)


@given(st.lists(_spec_tree, max_size=4))
def test_embedded_chapter_tree_round_trips_to_the_document_export(specs: list[_Spec]) -> None:
    """An empty tree is the one exception to full equality: it caches no identity on the tree
    itself (nothing ran, nothing to identify — `TraceTree.trace_id` stays `None`), so each
    independent `resolve_identity` call mints a fresh trace id, by the same rule that keeps two
    unrelated context-free captures from colliding
    (`test_two_span_less_captures_never_share_a_trace_id`). `write_trace` never persists an empty
    tree, so the two resolutions are never compared outside this property."""
    tree = _tree(specs)
    embedded = json.loads(_chapter(tree)["nt.chapterTree"])
    freestanding = json.loads(export_document(tree, TraceMetadata("s", ScenarioResult.SUCCESS)))
    if tree.roots:
        assert embedded == freestanding
    else:
        assert embedded["events"] == freestanding["events"] == []


@given(st.lists(_spec_tree, max_size=4))
def test_emitted_keys_are_always_a_subsequence_of_the_canonical_order(specs: list[_Spec]) -> None:
    keys = list(_chapter(_tree(specs)))
    positions = [CANONICAL_ORDER.index(key) for key in keys]
    assert positions == sorted(positions)
    assert len(set(keys)) == len(keys)


@given(st.lists(_spec_tree, max_size=4))
def test_error_level_holds_exactly_when_the_chapter_failed(specs: list[_Spec]) -> None:
    doc = _chapter(_tree(specs))
    assert (doc["level"] == "error") == (doc["nt.outcome"] == "failure")


def _span_less(specs: list[_Spec]) -> list[_Spec]:
    """The same shapes with every span context removed — a plain unit-test capture."""
    return [_Spec(s.outcome_kind, False, s.duration_nanos, _span_less(s.children)) for s in specs]


@given(st.lists(_spec_tree, max_size=4))
def test_the_trace_name_always_names_the_trace_id_that_was_emitted(specs: list[_Spec]) -> None:
    doc = _chapter(_tree(specs))
    assert doc["nt.traceName"] == TraceId(doc["trace_id"]).human_name()


@given(st.lists(_spec_tree, max_size=4))
def test_two_span_less_captures_never_share_a_trace_id(specs: list[_Spec]) -> None:
    """The reason the synthetic constant was retired: it made two unrelated captures
    indistinguishable, which is the one job `trace_id` exists to do. Story and chapter are
    *derived*, not generated, so they stay stable across the two runs."""
    first = _chapter(_tree(_span_less(specs)))
    second = _chapter(_tree(_span_less(specs)))

    assert first["trace_id"] != second["trace_id"]
    assert first["nt.storyId"] == second["nt.storyId"]
    assert first["nt.chapterId"] == second["nt.chapterId"]
    assert first["nt.title"] == second["nt.title"]


@given(st.lists(_spec_tree, max_size=4))
def test_a_chapter_and_the_canonical_entries_of_one_tree_name_the_same_trace(
    specs: list[_Spec],
) -> None:
    tree = _tree(specs)
    doc = _chapter(tree)

    named = {entry.trace_id for entry in entries_from_tree(tree)}
    assert named == ({doc["trace_id"]} if tree.roots else set())
