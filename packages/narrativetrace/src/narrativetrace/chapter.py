# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Exports a trace tree as one flat chapter object (``chapter.schema.json``).

``ChapterExporter``. A *chapter* is one service's complete contribution to a trace:
Layer 1+2 fields (timestamp/level/message/service/trace_id) plus chapter-specific Layer 3
``nt.*`` fields, with the full nested tree embedded as a JSON *string* under ``nt.chapterTree``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from narrativetrace.canonical import SCHEMA_VERSION
from narrativetrace.export import export_document
from narrativetrace.identity import TraceIdentity, resolve_identity, root_call_name
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw
from narrativetrace.render.base import TraceMetadata
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk

_DEFAULT_OUTCOME = "success"


def _outcome(root: TraceNode | None) -> str:
    """Maps the root node's outcome onto the chapter enum (a missing node reads as success)."""
    if root is None:
        return _DEFAULT_OUTCOME
    if isinstance(root.outcome, Returned):
        return "success"
    if isinstance(root.outcome, Threw):
        return "failure"
    if isinstance(root.outcome, Incomplete):
        return "partial"
    return _DEFAULT_OUTCOME


def _level(outcome: str) -> str:
    return "error" if outcome == "failure" else "info"


def _duration_millis(root: TraceNode | None) -> int:
    return root.duration_millis if root is not None else 0


def _message(title: str, duration_millis: int, outcome: str) -> str:
    return f"Chapter complete: {title} [{duration_millis}ms] {outcome}"


def _timestamp(clock: Callable[[], datetime] | None) -> str:
    """Formats the clock reading as UTC ISO-8601 with fixed millisecond precision.

    Unlike Java's ``Instant.toString()`` (which varies the fractional width), the width here is
    always three digits so chapter timestamps sort and diff as plain strings.
    """
    reading = clock() if clock is not None else datetime.now(UTC)
    if reading.tzinfo is None or reading.tzinfo.utcoffset(reading) is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return reading.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _count_entries(nodes: list[TraceNode], walk: TreeWalk | None = None) -> int:
    """Counts ``nodes`` and every descendant — one chapter entry per traced call."""
    walk = walk if walk is not None else TreeWalk()
    total = 0
    for node in nodes:
        total += 1
        if walk.stop_reason(node) is None:
            walk.enter(node)
            try:
                total += _count_entries(node.children, walk)
            finally:
                walk.exit(node)
    return total


def _write_header_fields(
    doc: dict[str, Any],
    identity: TraceIdentity,
    title: str,
    outcome: str,
    duration_millis: int,
    timestamp: str,
) -> None:
    doc["timestamp"] = timestamp
    doc["level"] = _level(outcome)
    doc["message"] = _message(title, duration_millis, outcome)
    # `service` and `trace_id` are required by chapter.schema.json and are never omitted: a tree
    # captured without any span still reports `unknown_service:python` and a generated trace id.
    doc["service"] = identity.service
    doc["trace_id"] = str(identity.trace_id)


def _write_schema_fields(
    doc: dict[str, Any], identity: TraceIdentity, title: str, outcome: str
) -> None:
    doc["nt.entryType"] = "chapter"
    doc["nt.storyId"] = identity.story_id
    doc["nt.chapterId"] = identity.chapter_id
    doc["nt.title"] = title
    doc["nt.outcome"] = outcome
    doc["nt.completionStatus"] = "complete"
    doc["nt.traceName"] = identity.trace_name
    doc["nt.schemaVersion"] = SCHEMA_VERSION


def _write_total_fields(
    doc: dict[str, Any], root: TraceNode | None, roots: list[TraceNode]
) -> None:
    """Emits the totals; the duration is omitted entirely when there is no root to measure."""
    if root is not None:
        doc["nt.totalDurationMs"] = root.duration_millis
    doc["nt.entryCount"] = _count_entries(roots)


def export_chapter(
    tree: TraceTree, metadata: TraceMetadata, *, clock: Callable[[], datetime] | None = None
) -> str:
    """Serialises a trace tree as a chapter JSON object.

    Args:
        tree: The captured tree; its first root supplies title, outcome and duration, and
            :func:`~narrativetrace.identity.resolve_identity` supplies the correlation fields —
            always present, derived or generated when no span was captured.
        metadata: Scenario metadata, used only for the embedded ``nt.chapterTree`` document.
        clock: Returns the chapter-completion instant. Defaults to :func:`datetime.now` in UTC;
            inject to make output deterministic.

    Returns:
        A JSON object string matching ``chapter.schema.json``, with the nested trace tree
        embedded as a JSON *string* under ``nt.chapterTree``.
    """
    if tree is None:
        raise ValueError("tree must not be None")
    if metadata is None:
        raise ValueError("metadata must not be None")
    root = tree.roots[0] if tree.roots else None
    identity = resolve_identity(tree)
    outcome = _outcome(root)
    title = root_call_name(tree.roots)
    doc: dict[str, Any] = {}
    _write_header_fields(doc, identity, title, outcome, _duration_millis(root), _timestamp(clock))
    _write_schema_fields(doc, identity, title, outcome)
    _write_total_fields(doc, root, tree.roots)
    doc["nt.chapterTree"] = export_document(tree, metadata)
    return json.dumps(doc, indent=2, ensure_ascii=False)
