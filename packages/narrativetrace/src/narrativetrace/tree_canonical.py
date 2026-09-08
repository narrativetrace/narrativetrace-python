# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Maps a finished :class:`~narrativetrace.tree.TraceTree` to flat canonical entries.

``TraceTreeCanonicalMapper``. The per-test ``.canonical.json`` artifact — the input of
cross-runtime conformance fixtures and of trace translation — is derived from the *captured tree*
after the run, not from the live event stream. Each node yields one ``method_enter`` and one
``method_exit`` entry in depth-first order, linked by span ids.

Unlike :func:`~narrativetrace.canonical.entry_from_event`, exit entries here carry the node's real
``code.namespace`` / ``code.function``: the tree still knows its signature, whereas an exit event
only knows its span name.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from narrativetrace.canonical import (
    SCHEMA_VERSION,
    CanonicalEntry,
    ParameterEntry,
    entry_to_json,
    service_or_unknown,
    with_thread_identity,
)
from narrativetrace.identity import TraceIdentity, resolve_identity
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned, Threw, TraceOutcome
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk

_REDACTED = "[REDACTED]"
_NANOS_PER_MILLI = 1_000_000


@dataclass(slots=True)
class _SpanIdCounter:
    """Hands out deterministic synthetic span ids so nesting survives a context-free tree."""

    issued: int = 0

    def next_id(self) -> str:
        self.issued += 1
        return f"{self.issued:016x}"


def _span_id_of(node: TraceNode, counter: _SpanIdCounter) -> str:
    if node.span_context is not None:
        return str(node.span_context.span_id)
    return counter.next_id()


def _parameters(sig: MethodSignature) -> list[ParameterEntry] | None:
    if not sig.parameters:
        return None
    return [
        ParameterEntry(
            p.name, _REDACTED if p.redacted else p.rendered_value, p.redacted, p.type_name
        )
        for p in sig.parameters
    ]


def _outcome_name(outcome: TraceOutcome | None) -> str:
    if isinstance(outcome, Returned):
        return "success"
    if isinstance(outcome, Threw):
        return "failure"
    return "incomplete"


def _timestamp(nanos: int) -> str:
    """Formats a monotonic reading as the epoch-based instant Java's synthetic base produces.

    Node clocks are monotonic nanos with an arbitrary origin. A tree has no wall-clock anchor, so
    the reading is treated as milliseconds since the epoch — deterministic, and the same rule the
    Java mapper applies to a context-free tree.
    """
    moment = datetime.fromtimestamp((nanos // _NANOS_PER_MILLI) / 1000, tz=UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _with_resource(entry: CanonicalEntry, effective: SpanContext | None) -> CanonicalEntry:
    """Adds the service, environment and process resource fields the effective context carries.

    No context leaves the entry at its defaults, which already say ``unknown_service:python`` and
    ``null`` — the schema's spelling for "nobody told us", not a guess. ``nt.traceName`` is *not*
    set here: it follows the trace id the entry actually carries, not the context it was read off.
    """
    if effective is None:
        return entry
    return replace(
        entry,
        service=service_or_unknown(effective.service_name),
        environment=effective.environment,
        host_name=effective.host_name,
        process_pid=effective.process_pid,
        process_runtime_version=effective.runtime_version,
    )


def _common_fields(
    node: TraceNode, span_id: str, parent_span_id: str | None, identity: TraceIdentity
) -> CanonicalEntry:
    """Identity and correlation shared by one node's enter and exit entries.

    Trace-scoped fields are read off the node's *own* context when it has one and off the tree's
    resolved identity otherwise — never regenerated per node, or a context-free child would split
    its own trace's identity. ``nt.traceName`` is derived from whichever trace id won, so the two
    can neither disagree nor go missing.
    """
    sig = node.signature
    own = node.span_context
    trace_id = own.trace_id if own is not None else identity.trace_id
    base = CanonicalEntry(
        timestamp="",
        level="",
        message="",
        nt_schema_version=SCHEMA_VERSION,
        trace_id=str(trace_id),
        span_id=span_id,
        parent_span_id=parent_span_id,
        code_namespace=sig.class_name,
        code_function=sig.method_name,
        nt_story_id=_story_id(own, identity),
        nt_chapter_id=_chapter_id(own, identity),
        nt_package=sig.package_name,
        nt_trace_name=trace_id.human_name(),
    )
    effective = own if own is not None else identity.inherited
    return with_thread_identity(_with_resource(base, effective), node.thread)


def _story_id(own: SpanContext | None, identity: TraceIdentity) -> str:
    if own is not None and own.story_id is not None:
        return own.story_id
    return identity.story_id


def _chapter_id(own: SpanContext | None, identity: TraceIdentity) -> str:
    if own is not None and own.chapter_id is not None:
        return own.chapter_id
    return identity.chapter_id


def _enter_entry(
    node: TraceNode, span_id: str, parent_span_id: str | None, identity: TraceIdentity
) -> CanonicalEntry:
    sig = node.signature
    return replace(
        _common_fields(node, span_id, parent_span_id, identity),
        timestamp=_timestamp(node.start_time_nanos),
        level="trace",
        message=f"→ {sig.class_name}.{sig.method_name}",
        nt_event_type="method_enter",
        nt_return_type=sig.return_type,
        nt_narration_template=sig.narration_template,
        nt_parameters=_parameters(sig),
    )


def _exit_message(sig: MethodSignature, outcome: TraceOutcome | None) -> str:
    if isinstance(outcome, Threw):
        return f"!! {type(outcome.exception).__name__}: {outcome.exception}"
    return f"← {sig.class_name}.{sig.method_name}"


def _exit_entry(
    node: TraceNode, span_id: str, parent_span_id: str | None, identity: TraceIdentity
) -> CanonicalEntry:
    sig, outcome = node.signature, node.outcome
    threw = outcome if isinstance(outcome, Threw) else None
    returned = outcome if isinstance(outcome, Returned) else None
    return replace(
        _common_fields(node, span_id, parent_span_id, identity),
        timestamp=_timestamp(node.start_time_nanos + node.duration_nanos),
        level="error" if threw is not None else "trace",
        message=_exit_message(sig, outcome),
        nt_event_type="method_exit",
        nt_outcome=_outcome_name(outcome),
        duration_ms=node.duration_millis,
        nt_return_value=returned.rendered_value if returned is not None else None,
        exception_type=type(threw.exception).__name__ if threw is not None else None,
        exception_message=str(threw.exception) if threw is not None else None,
        nt_exception_package=(
            getattr(type(threw.exception), "__module__", None) if threw is not None else None
        ),
    )


def _append_node(
    entries: list[CanonicalEntry],
    node: TraceNode,
    parent_span_id: str | None,
    counter: _SpanIdCounter,
    identity: TraceIdentity,
    walk: TreeWalk | None = None,
) -> None:
    walk = walk if walk is not None else TreeWalk()
    span_id = _span_id_of(node, counter)
    entries.append(_enter_entry(node, span_id, parent_span_id, identity))
    if walk.stop_reason(node) is None:
        walk.enter(node)
        try:
            for child in node.children:
                _append_node(entries, child, span_id, counter, identity, walk)
        finally:
            walk.exit(node)
    entries.append(_exit_entry(node, span_id, parent_span_id, identity))


def entries_from_tree(tree: TraceTree) -> list[CanonicalEntry]:
    """Flattens a tree into enter/exit canonical entries, depth-first, roots in order.

    Raises:
        ValueError: if ``tree`` is ``None`` — an absent tree is a caller bug, not an empty run.
    """
    if tree is None:
        raise ValueError("tree must not be None")
    entries: list[CanonicalEntry] = []
    counter = _SpanIdCounter()
    identity = resolve_identity(tree)
    for root in tree.roots:
        _append_node(entries, root, None, counter, identity)
    assert len(entries) == 2 * _count_nodes(tree.roots), "every node yields one enter and one exit"
    return entries


def _count_nodes(nodes: list[TraceNode], walk: TreeWalk | None = None) -> int:
    walk = walk if walk is not None else TreeWalk()
    total = 0
    for node in nodes:
        total += 1
        if walk.stop_reason(node) is None:
            walk.enter(node)
            try:
                total += _count_nodes(node.children, walk)
            finally:
                walk.exit(node)
    return total


def export_canonical_entries(tree: TraceTree) -> str:
    """Serialises a tree as the ``.canonical.json`` artifact: a JSON array of canonical entries.

    The machine-facing companion to the human-facing ``.md`` and the nested ``.json``: one flat
    array a cross-runtime conformance runner can compare element by element, every element valid
    against ``entry.schema.json``.
    """
    rendered = ",\n".join(entry_to_json(entry) for entry in entries_from_tree(tree))
    return f"[\n{rendered}\n]" if rendered else "[]"
