# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Flattens a trace tree into a canonical JSON event stream.

``JsonExporter``. Each node becomes two events — an ``enter`` and a matching
``exit`` — with parent-child structure preserved through span ids and ``parentId`` rather than
nested objects. Consumers parse fields, so this builds Python dicts and serialises with
:func:`json.dumps` (``ensure_ascii=False`` keeps unicode while still escaping control characters,
matching Java's ``JsonEscape``).

The richer per-service *chapter* schema (``nt.entryType`` / ``schemaVersion`` / story/chapter ids,
Java ``ChapterExporter`` / ``CanonicalEntry``) is a follow-up; this module ports the trace-file
event-stream form used by the pytest ``.json`` companion.
"""

from __future__ import annotations

import json
from typing import Any

from narrativetrace.concurrency import ConcurrencyInfo
from narrativetrace.identity import resolve_identity
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.base import TraceMetadata
from narrativetrace.signature import ParameterCapture
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import CYCLE_MARKER, DEPTH_LIMIT_MARKER, TreeWalk

_TRACE_FIELDS = (
    "service_name",
    "service_version",
    "environment",
    "http_method",
    "http_route",
    "client_ip",
    "enduser_id",
    "session_id",
    "tenant_id",
)
_TRACE_KEYS = {
    "service_name": "serviceName",
    "service_version": "serviceVersion",
    "environment": "environment",
    "http_method": "httpMethod",
    "http_route": "httpRoute",
    "client_ip": "clientIp",
    "enduser_id": "enduserId",
    "session_id": "sessionId",
    "tenant_id": "tenantId",
}


def _trace_block(tree: TraceTree) -> dict[str, Any]:
    """Builds the ``trace`` block, always: identity comes from the shared
    :func:`~narrativetrace.identity.resolve_identity`, so this embedded document names the same
    trace as the chapter that embeds it and the canonical entries flattened from the same tree
    (this is the third emitter that must resolve identity the same way).
    ``traceId``/``traceName`` are therefore always present; the
    request-scoped fields stay conditional on a real inherited span context — a generated identity
    knows which trace this is and nothing about who called it.
    """
    identity = resolve_identity(tree)
    block: dict[str, Any] = {
        "traceId": str(identity.trace_id),
        "traceName": identity.trace_name,
    }
    inherited = identity.inherited
    if inherited is not None:
        for field in _TRACE_FIELDS:
            value = getattr(inherited, field)
            if value is not None:
                block[_TRACE_KEYS[field]] = str(value)
    return block


def _kebab_kind(info: ConcurrencyInfo) -> str:
    return info.kind.name.lower().replace("_", "-")


def _concurrency_block(info: ConcurrencyInfo) -> dict[str, Any]:
    return {
        "groupId": info.group_id,
        "threadName": info.thread_name if info.thread_name is not None else info.task_label,
        "threadId": info.thread_id,
        "virtual": info.virtual,
        "kind": _kebab_kind(info),
    }


def _param_object(param: ParameterCapture) -> dict[str, Any]:
    """Renders one parameter; ``value`` is always a string, as the schema requires.

    Below DETAIL the capture holds an empty rendered value. Emitting ``null`` for it — which this
    did until the writer-validated conformance test caught it — breaks
    ``chapter-tree.schema.json``, where ``value`` is a required string. An empty string says the
    same thing and stays in contract, matching Java's ``JsonExporter``.
    """
    if param.redacted:
        return {"name": param.name, "value": "[REDACTED]", "redacted": True}
    return {"name": param.name, "value": param.rendered_value, "redacted": False}


def _span_id(node: TraceNode) -> str:
    if node.span_context is not None:
        return str(node.span_context.span_id)
    return str(id(node))


def _enter_event(
    node: TraceNode, span_id: str, depth: int, parent_id: str | None
) -> dict[str, Any]:
    sig = node.signature
    event: dict[str, Any] = {
        "spanId": span_id,
        "type": "enter",
        "className": sig.class_name,
        "methodName": sig.method_name,
        "parameters": [_param_object(p) for p in sig.parameters],
    }
    if node.span_context is not None and node.span_context.parent_span_id is not None:
        event["parentSpanId"] = str(node.span_context.parent_span_id)
    if node.concurrency is not None:
        event["concurrency"] = _concurrency_block(node.concurrency)
    event["depth"] = depth
    event["parentId"] = parent_id
    return event


def _exit_event(node: TraceNode, span_id: str, depth: int, parent_id: str | None) -> dict[str, Any]:
    sig = node.signature
    event: dict[str, Any] = {
        "spanId": span_id,
        "type": "exit",
        "className": sig.class_name,
        "methodName": sig.method_name,
    }
    _append_outcome(event, node.outcome)
    event["durationMs"] = node.duration_millis
    event["depth"] = depth
    event["parentId"] = parent_id
    return event


def _append_outcome(event: dict[str, Any], outcome: TraceOutcome | None) -> None:
    if isinstance(outcome, Returned):
        event["outcome"] = "returned"
        event["returnValue"] = "null" if outcome.rendered_value is None else outcome.rendered_value
    elif isinstance(outcome, Threw):
        event["outcome"] = "threw"
        event["errorType"] = type(outcome.exception).__name__
        event["errorMessage"] = str(outcome.exception)
    elif isinstance(outcome, Incomplete):
        event["outcome"] = "incomplete"
    else:
        event["outcome"] = "returned"


_TRUNCATED_REASON = {DEPTH_LIMIT_MARKER: "depth-limit", CYCLE_MARKER: "cycle"}


def _flatten(
    node: TraceNode,
    depth: int,
    parent_id: str | None,
    events: list[dict[str, Any]],
    walk: TreeWalk | None = None,
) -> None:
    walk = walk if walk is not None else TreeWalk()
    span_id = _span_id(node)
    events.append(_enter_event(node, span_id, depth, parent_id))
    stop_reason = walk.stop_reason(node)
    if stop_reason is None:
        walk.enter(node)
        try:
            for child in node.children:
                _flatten(child, depth + 1, span_id, events, walk)
        finally:
            walk.exit(node)
    exit_event = _exit_event(node, span_id, depth, parent_id)
    if stop_reason is not None and node.children:
        exit_event["truncated"] = _TRUNCATED_REASON[stop_reason]
    events.append(exit_event)


def _events(tree: TraceTree) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for root in tree.roots:
        _flatten(root, 0, None, events)
    return events


def _document(tree: TraceTree, metadata: TraceMetadata | None) -> dict[str, Any]:
    doc: dict[str, Any] = {}
    if metadata is not None:
        # The wire spelling, never the display one: chapter-tree.schema.json constrains
        # scenario.result to success/error, and PASSED/FAILED here failed the schema silently.
        scenario: dict[str, Any] = {"name": metadata.scenario, "result": metadata.result.wire_name}
        if tree.roots:
            scenario["durationMs"] = tree.roots[0].duration_millis
        doc["version"] = "1.0"
        doc["scenario"] = scenario
    doc["trace"] = _trace_block(tree)
    doc["events"] = _events(tree)
    return doc


def export(tree: TraceTree) -> str:
    """Serialises a trace tree to canonical JSON (trace block + flattened event stream)."""
    return json.dumps(_document(tree, None), indent=2, ensure_ascii=False)


def export_document(tree: TraceTree, metadata: TraceMetadata) -> str:
    """Serialises a trace as a full document with a ``version`` and ``scenario`` header."""
    return json.dumps(_document(tree, metadata), indent=2, ensure_ascii=False)
