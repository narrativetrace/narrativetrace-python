# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the canonical JSON export (structure + round-trip)."""

from __future__ import annotations

import json
import re

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.export import export, export_document
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.metadata import HttpRoute
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree

MS = 1_000_000
TRACE = TraceId("0" * 32)


def _span(hex_char: str, parent: SpanId | None = None, **kw: object) -> SpanContext:
    return SpanContext(trace_id=TRACE, span_id=SpanId(hex_char * 16), parent_span_id=parent, **kw)  # type: ignore[arg-type]


def _tree(*roots: TraceNode) -> TraceTree:
    return TraceTree(list(roots))


class TestStructure:
    def test_enter_and_exit_events_per_node(self) -> None:
        node = TraceNode(
            MethodSignature("Svc", "run", [ParameterCapture("id", "7")]),
            [],
            Returned("ok"),
            span_context=_span("a"),
        )
        doc = json.loads(export(_tree(node)))
        assert [e["type"] for e in doc["events"]] == ["enter", "exit"]
        enter, exit_ = doc["events"]
        assert enter["className"] == "Svc"
        assert enter["parameters"] == [{"name": "id", "value": "7", "redacted": False}]
        assert exit_["outcome"] == "returned"
        assert exit_["returnValue"] == "ok"

    def test_trace_block_from_root_span(self) -> None:
        node = TraceNode(
            MethodSignature("Svc", "run", []),
            [],
            Returned("ok"),
            span_context=_span("a", http_route=HttpRoute.of("/orders"), service_name="orders"),
        )
        doc = json.loads(export(_tree(node)))
        assert doc["trace"]["traceId"] == "0" * 32
        assert doc["trace"]["traceName"] == "red fox runs"
        assert doc["trace"]["httpRoute"] == "/orders"
        assert doc["trace"]["serviceName"] == "orders"

    def test_trace_block_is_present_even_when_no_node_kept_a_span_context(self) -> None:
        """26c, third emitter: a chapter can no longer name a trace whose embedded tree names
        none — the block is always emitted, resolved the same way `chapter.py` resolves it."""
        node = TraceNode(MethodSignature("Svc", "run", []), [], Returned("ok"))

        doc = json.loads(export(_tree(node)))

        assert re.fullmatch(r"[0-9a-f]{32}", doc["trace"]["traceId"])
        assert re.fullmatch(r"[a-z]+ [a-z]+ [a-z]+", doc["trace"]["traceName"])
        assert "serviceName" not in doc["trace"]
        assert "httpRoute" not in doc["trace"]

    def test_trace_block_inherits_from_a_descendant_when_no_root_kept_its_context(self) -> None:
        child = TraceNode(
            MethodSignature("Payment", "charge", []),
            [],
            Returned("ok"),
            span_context=_span("b", service_name="orders"),
        )
        root = TraceNode(MethodSignature("Svc", "run", []), [child], Returned("ok"))

        doc = json.loads(export(_tree(root)))

        assert doc["trace"]["traceId"] == "0" * 32
        assert doc["trace"]["serviceName"] == "orders"

    def test_nesting_via_parent_id(self) -> None:
        child = TraceNode(
            MethodSignature("Svc", "child", []),
            [],
            Returned("c"),
            span_context=_span("b", parent=SpanId("a" * 16)),
        )
        parent = TraceNode(
            MethodSignature("Svc", "parent", []), [child], Returned("p"), span_context=_span("a")
        )
        doc = json.loads(export(_tree(parent)))
        enters = {
            e["className"] + "." + e["methodName"]: e for e in doc["events"] if e["type"] == "enter"
        }
        assert enters["Svc.child"]["parentId"] == "a" * 16
        assert enters["Svc.child"]["depth"] == 1
        assert enters["Svc.parent"]["parentId"] is None

    def test_threw_outcome(self) -> None:
        node = TraceNode(
            MethodSignature("S", "m", []), [], Threw(ValueError("boom")), span_context=_span("a")
        )
        exit_ = json.loads(export(_tree(node)))["events"][1]
        assert exit_["outcome"] == "threw"
        assert exit_["errorType"] == "ValueError"
        assert exit_["errorMessage"] == "boom"

    def test_incomplete_outcome(self) -> None:
        node = TraceNode(MethodSignature("S", "m", []), [], Incomplete(), span_context=_span("a"))
        assert json.loads(export(_tree(node)))["events"][1]["outcome"] == "incomplete"

    def test_redacted_param(self) -> None:
        node = TraceNode(
            MethodSignature("S", "m", [ParameterCapture("pw", "", redacted=True)]),
            [],
            Returned("x"),
            span_context=_span("a"),
        )
        param = json.loads(export(_tree(node)))["events"][0]["parameters"][0]
        assert param == {"name": "pw", "value": "[REDACTED]", "redacted": True}

    def test_concurrency_block_kebab_kind(self) -> None:
        node = TraceNode(
            MethodSignature("S", "m", []),
            [],
            Returned("x"),
            span_context=_span("a"),
            concurrency=ConcurrencyInfo("g1", ConcurrencyKind.FIRE_AND_FORGET, thread_name="w"),
        )
        block = json.loads(export(_tree(node)))["events"][0]["concurrency"]
        assert block["groupId"] == "g1"
        assert block["kind"] == "fire-and-forget"
        assert block["threadName"] == "w"

    def test_void_return_value_is_null_string(self) -> None:
        node = TraceNode(MethodSignature("S", "m", []), [], Returned(None), span_context=_span("a"))
        assert json.loads(export(_tree(node)))["events"][1]["returnValue"] == "null"


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): flattening used unbounded native recursion with no
    depth bound or cycle guard -- both a cycle and a pathologically deep chain crashed with an
    uncaught RecursionError."""

    def test_a_self_referential_node_does_not_crash_flattening(self) -> None:
        node = TraceNode(MethodSignature("S", "m", []), [], Returned("x"))
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        doc = json.loads(export(_tree(node)))
        assert any(e.get("truncated") == "cycle" for e in doc["events"])

    def test_a_ten_thousand_deep_chain_is_truncated_not_crashed(self) -> None:
        node = TraceNode(MethodSignature("S", "leaf", []), [], Returned("x"))
        for _ in range(10_000):
            node = TraceNode(MethodSignature("S", "wrap", []), [node], Returned("x"))
        doc = json.loads(export(_tree(node)))
        assert len(doc["events"]) < 2000
        assert any(e.get("truncated") == "depth-limit" for e in doc["events"])


class TestDocument:
    def test_document_header(self) -> None:
        node = TraceNode(
            MethodSignature("S", "m", []),
            [],
            Returned("x"),
            duration_nanos=5 * MS,
            span_context=_span("a"),
        )
        doc = json.loads(
            export_document(_tree(node), TraceMetadata("happy", ScenarioResult.SUCCESS))
        )
        assert doc["version"] == "1.0"
        assert doc["scenario"] == {"name": "happy", "result": "success", "durationMs": 5}


class TestRoundTrip:
    def test_export_is_valid_json_and_reparses(self) -> None:
        child = TraceNode(
            MethodSignature("S", "child", []),
            [],
            Threw(ValueError('x\n"y')),
            span_context=_span("b", parent=SpanId("a" * 16)),
        )
        parent = TraceNode(
            MethodSignature("S", "parent", []), [child], Returned("p"), span_context=_span("a")
        )
        text = export(_tree(parent))
        reparsed = json.loads(text)
        assert len(reparsed["events"]) == 4  # 2 nodes x (enter + exit)

    def test_empty_tree_still_names_a_trace(self) -> None:
        """Inverted, not deleted: an empty tree used to omit the `trace` block entirely.
        `resolve_identity` generates a fresh identity for it, same as `chapter.py` already does."""
        doc = json.loads(export(_tree()))

        assert doc["events"] == []
        assert re.fullmatch(r"[0-9a-f]{32}", doc["trace"]["traceId"])
