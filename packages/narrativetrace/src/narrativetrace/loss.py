# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What a trace is missing, and why.

``TraceLoss``. Both of the best-effort path's loss modes report through one type, so a
reader is never left guessing whether a short trace means "nothing happened" or "we dropped it".
The synchronous log stream is unaffected by either — it is the durable record, and a run that lost
events here still narrated them there.

llmNote: a non-:meth:`TraceLoss.none` loss makes the captured tree an *incomplete* view of the
run, not a wrong one. Dropped events can also leave a span with no exit, which surfaces as
:class:`~narrativetrace.outcomes.Incomplete` — so an outcome, not only a branch, may be missing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TraceLoss:
    """Counts of what a run lost: shed events, refused async scopes, and discarded late work.

    ``dropped_events`` are events the bounded buffer shed under load; ``refused_scopes`` are worker
    scopes whose spans were refused *whole* because the adoption cap was full — each one an async
    subtree absent from the tree — and ``refused_spans`` is how many spans those refusals cost.
    ``discarded_spans`` (a bug-hunt finding) counts worker spans a request's own stack refused to
    take back because it had already been reset/closed by the time the worker finished — a
    request's own background tail, not an incomplete *current* trace, so it is deliberately excluded
    from :meth:`any`. All four are cumulative for the reading context, so a caller brackets a
    scenario with two readings and takes :meth:`since` to attribute loss to it.
    """

    dropped_events: int
    refused_scopes: int
    refused_spans: int
    discarded_spans: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.dropped_events,
            self.refused_scopes,
            self.refused_spans,
            self.discarded_spans,
        )
        if any(count < 0 for count in counts):
            raise ValueError("Loss counts must not be negative")

    @classmethod
    def none(cls) -> TraceLoss:
        """The "nothing was lost" reading."""
        return _NONE

    def any(self) -> bool:
        """Whether anything was lost, i.e. whether the captured tree is an incomplete view.

        A refused *span* count without a refused scope is not loss on its own: it is the size of a
        refusal, and the refusal is the event. ``discarded_spans`` is excluded for the same reason
        as its own docstring: it is a request's late background tail, not part of this trace.
        """
        return self.dropped_events > 0 or self.refused_scopes > 0

    def plus(self, other: TraceLoss) -> TraceLoss:
        """Sums two readings, for reporting a suite total over per-scenario ones."""
        return TraceLoss(
            self.dropped_events + other.dropped_events,
            self.refused_scopes + other.refused_scopes,
            self.refused_spans + other.refused_spans,
            self.discarded_spans + other.discarded_spans,
        )

    def since(self, earlier: TraceLoss) -> TraceLoss:
        """The loss between an earlier reading and this one, floored at zero.

        Counters only grow, so a reversed pair is a caller error rather than a negative loss.
        """
        return TraceLoss(
            max(0, self.dropped_events - earlier.dropped_events),
            max(0, self.refused_scopes - earlier.refused_scopes),
            max(0, self.refused_spans - earlier.refused_spans),
            max(0, self.discarded_spans - earlier.discarded_spans),
        )


_NONE = TraceLoss(0, 0, 0)
