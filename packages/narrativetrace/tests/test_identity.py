# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the one identity resolution both exporters share.

`chapter.py` and `tree_canonical.py` must give the same answer for the same tree — resolving it
twice, independently, is how a chapter and its own `.canonical.json` end up naming two different
traces (the defect Java found before `TraceIdentity` existed).
"""

from __future__ import annotations

import pytest

from narrativetrace.canonical import UNKNOWN_SERVICE
from narrativetrace.identity import UNKNOWN_CALL, resolve_identity, root_call_name
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree

TRACE = TraceId("0" * 32)


def _span(**kw: object) -> SpanContext:
    fields: dict[str, object] = {"trace_id": TRACE, "span_id": SpanId("a" * 16)}
    fields.update(kw)
    return SpanContext(**fields)  # type: ignore[arg-type]


def _node(
    class_name: str = "OrderService", method_name: str = "place_order", **kw: object
) -> TraceNode:
    fields: dict[str, object] = {
        "signature": MethodSignature(class_name, method_name, []),
        "children": [],
    }
    fields.update(kw)
    return TraceNode(**fields)  # type: ignore[arg-type]


class TestTraceId:
    def test_adopts_the_id_the_tree_already_resolved(self) -> None:
        tree = TraceTree([_node()], TraceId("c" * 32))

        assert resolve_identity(tree).trace_id == TraceId("c" * 32)

    def test_inherits_a_span_context_found_anywhere_in_the_tree(self) -> None:
        deep = _node("Inventory", "reserve", span_context=_span())

        assert resolve_identity(TraceTree([_node(children=[deep])])).trace_id == TRACE

    def test_an_empty_tree_is_given_a_fresh_id_because_the_field_is_required(self) -> None:
        """The tree keeps no identity, but its chapter still has to carry one."""
        identity = resolve_identity(TraceTree([]))

        assert len(str(identity.trace_id)) == 32
        assert str(identity.trace_id) != "0" * 32

    def test_two_empty_trees_are_not_declared_to_be_the_same_trace(self) -> None:
        assert resolve_identity(TraceTree([])).trace_id != resolve_identity(TraceTree([])).trace_id


class TestTraceName:
    def test_names_the_resolved_trace_id_rather_than_any_context(self) -> None:
        identity = resolve_identity(TraceTree([_node(span_context=_span())]))

        assert identity.trace_name == TRACE.human_name()

    def test_agrees_with_a_generated_id_too(self) -> None:
        identity = resolve_identity(TraceTree([_node()]))

        assert identity.trace_name == identity.trace_id.human_name()


class TestStoryAndChapter:
    def test_derives_the_story_from_the_first_root_level_call(self) -> None:
        identity = resolve_identity(TraceTree([_node()]))

        assert identity.story_id == "OrderService.place_order"
        assert identity.chapter_id == identity.story_id

    def test_the_inherited_story_beats_the_derived_one(self) -> None:
        identity = resolve_identity(TraceTree([_node(span_context=_span(story_id="checkout"))]))

        assert identity.story_id == "checkout"

    def test_the_chapter_falls_back_to_the_story_when_the_context_names_none(self) -> None:
        identity = resolve_identity(TraceTree([_node(span_context=_span(story_id="checkout"))]))

        assert identity.chapter_id == "checkout"

    def test_the_inherited_chapter_is_kept_when_the_context_names_one(self) -> None:
        span = _span(story_id="checkout", chapter_id="checkout#1")

        assert resolve_identity(TraceTree([_node(span_context=span)])).chapter_id == "checkout#1"

    def test_an_empty_tree_takes_the_same_unknown_fallback_the_title_uses(self) -> None:
        identity = resolve_identity(TraceTree([]))

        assert (identity.story_id, identity.chapter_id) == (UNKNOWN_CALL, UNKNOWN_CALL)

    def test_a_deep_context_answers_for_a_context_free_root(self) -> None:
        deep = _node("Inventory", "reserve", span_context=_span(story_id="checkout"))

        assert resolve_identity(TraceTree([_node(children=[deep])])).story_id == "checkout"


class TestService:
    def test_reports_the_inherited_contexts_service(self) -> None:
        identity = resolve_identity(TraceTree([_node(span_context=_span(service_name="orders"))]))

        assert identity.service == "orders"

    def test_a_context_deep_in_a_mixed_tree_still_names_the_service(self) -> None:
        deep = _node("Inventory", "reserve", span_context=_span(service_name="orders"))

        assert resolve_identity(TraceTree([_node(children=[deep])])).service == "orders"

    def test_falls_back_when_no_context_named_one(self) -> None:
        assert resolve_identity(TraceTree([_node()])).service == UNKNOWN_SERVICE

    def test_a_blank_service_name_is_not_a_name(self) -> None:
        span = _span(service_name="   ")

        assert resolve_identity(TraceTree([_node(span_context=span)])).service == UNKNOWN_SERVICE


class TestRootCallName:
    def test_names_the_first_root(self) -> None:
        assert root_call_name([_node(), _node("Inventory", "reserve")]) == (
            "OrderService.place_order"
        )

    def test_has_nothing_to_name_without_roots(self) -> None:
        assert root_call_name([]) == UNKNOWN_CALL


class TestGuards:
    def test_rejects_a_missing_tree(self) -> None:
        with pytest.raises(ValueError, match=r"\Atree must not be None\Z"):
            resolve_identity(None)  # type: ignore[arg-type]
