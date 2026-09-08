# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Immutable node in a captured trace tree.

``TraceNode`` — the main read model for renderers, exporters, and tests. One node
usually represents one method invocation, though synthetic launcher nodes (fire-and-forget)
also appear and may carry a ``None`` outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from narrativetrace.concurrency import ConcurrencyInfo, ThreadIdentity
from narrativetrace.outcomes import TraceOutcome
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext

_NANOS_PER_MILLI = 1_000_000


@dataclass(frozen=True, slots=True)
class TraceNode:
    """A method invocation with its children, outcome, timing, and correlation metadata."""

    signature: MethodSignature
    children: list[TraceNode] = field(default_factory=list)
    outcome: TraceOutcome | None = None
    duration_nanos: int = 0
    start_time_nanos: int = 0
    concurrency: ConcurrencyInfo | None = None
    span_context: SpanContext | None = None
    thread: ThreadIdentity | None = None

    @property
    def duration_millis(self) -> int:
        """``duration_nanos`` truncated to whole milliseconds."""
        return self.duration_nanos // _NANOS_PER_MILLI

    def _own_fields(self) -> tuple[object, ...]:
        return (
            self.signature,
            self.outcome,
            self.duration_nanos,
            self.start_time_nanos,
            self.concurrency,
            self.span_context,
            self.thread,
        )

    def __eq__(self, other: object) -> bool:
        """Structural equality, iterative rather than recursive.

        ``children`` is a plain mutable list even under ``frozen=True``, so a hand-built or
        replayed tree can be deep enough or cyclic enough to blow the call stack -- the same risk
        every tree-walking renderer already guards against with
        :class:`~narrativetrace.tree_walk.TreeWalk`. The dataclass-generated ``__eq__`` this
        replaces recurses once per node pair (confirmed: a 5,000-node chain overflows it), and a
        pair of structurally-cyclic-but-not-identical trees never terminates at all. An explicit
        worklist sidesteps both: depth costs heap, not stack, and a ``(id(a), id(b))`` pair seen
        twice is treated as consistent rather than re-walked -- the standard coinductive reading of
        equality for a graph that may contain cycles.
        """
        if other.__class__ is not TraceNode:
            return NotImplemented
        stack: list[tuple[TraceNode, TraceNode]] = [(self, other)]
        seen: set[tuple[int, int]] = set()
        while stack:
            left, right = stack.pop()
            pair = (id(left), id(right))
            if pair in seen:
                continue
            seen.add(pair)
            if left._own_fields() != right._own_fields():
                return False
            if len(left.children) != len(right.children):
                return False
            stack.extend(zip(left.children, right.children, strict=True))
        return True

    # children is an unhashable list, so no TraceNode was ever hashable -- the dataclass-generated
    # __hash__ this replaces only discovered that by raising TypeError partway through hashing the
    # field tuple. Declaring it None makes the existing contract explicit instead of accidental.
    __hash__ = None  # type: ignore[assignment]
