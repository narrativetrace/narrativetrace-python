# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Child grouping and sequential-async detection for concurrency rendering.

``ChildSegment``, ``SequentialAsyncDetector`` and ``SequentialAsyncResult``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from narrativetrace.concurrency import ConcurrencyKind
from narrativetrace.nodes import TraceNode

_NANOS_PER_MILLI = 1_000_000


@dataclass(slots=True)
class ChildSegment:
    """A run of consecutive children sharing a concurrency group (``None`` = sequential)."""

    group_id: str | None
    nodes: list[TraceNode] = field(default_factory=list)

    def is_fire_and_forget(self) -> bool:
        first = self.nodes[0]
        return (
            first.concurrency is not None
            and first.concurrency.kind is ConcurrencyKind.FIRE_AND_FORGET
        )


def partition(children: list[TraceNode]) -> list[ChildSegment]:
    """Groups consecutive children by concurrency ``group_id`` for rendering."""
    segments: list[ChildSegment] = []
    for child in children:
        group_id = child.concurrency.group_id if child.concurrency is not None else None
        last = segments[-1] if segments else None
        if group_id is not None and last is not None and group_id == last.group_id:
            last.nodes.append(child)
        else:
            segments.append(ChildSegment(group_id, [child]))
    return segments


class Classification(Enum):
    NONE = "none"
    SEQUENTIAL_ASYNC = "sequential_async"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class SequentialAsyncResult:
    """Classification of a fork group's concurrency plus sequential/parallelisable costs."""

    classification: Classification
    total_nanos: int
    max_nanos: int

    @property
    def is_sequential_async(self) -> bool:
        return self.classification is Classification.SEQUENTIAL_ASYNC

    @property
    def total_millis(self) -> int:
        return self.total_nanos // _NANOS_PER_MILLI

    @property
    def parallelizable_millis(self) -> int:
        return self.max_nanos // _NANOS_PER_MILLI


_NONE_RESULT = SequentialAsyncResult(Classification.NONE, 0, 0)


def analyze(members: list[TraceNode]) -> SequentialAsyncResult:
    """Detects whether concurrent members were awaited sequentially (a missed parallelisation)."""
    if len(members) < 2:
        return _NONE_RESULT
    ordered = sorted(members, key=lambda n: n.start_time_nanos)
    overlapping = 0
    for i in range(1, len(ordered)):
        prev_end = ordered[i - 1].start_time_nanos + ordered[i - 1].duration_nanos
        if ordered[i].start_time_nanos < prev_end:
            overlapping += 1
    total = sum(n.duration_nanos for n in members)
    longest = max((n.duration_nanos for n in members), default=0)
    if overlapping == 0:
        return SequentialAsyncResult(Classification.SEQUENTIAL_ASYNC, total, longest)
    if overlapping < len(ordered) - 1:
        return SequentialAsyncResult(Classification.MIXED, total, longest)
    return _NONE_RESULT
