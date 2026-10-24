# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Converts the monotonic clock NarrativeTrace events carry into Unix-epoch nanoseconds.

``MonotonicToEpoch``. Trace events are stamped with :func:`time.perf_counter_ns` (a monotonic
clock with an arbitrary origin); OpenTelemetry timestamps are Unix-epoch nanoseconds. One anchor
pairs a wall-clock reading with a monotonic reading, and every event time is placed at its offset
from that anchor.
"""

from __future__ import annotations

import time


class MonotonicToEpoch:
    """Places monotonic readings on the epoch timeline through one (epoch, monotonic) anchor.

    Edge case: an event captured *before* the anchor has a negative offset and converts to an
    epoch time before the anchor's epoch time -- it is not clamped.
    """

    __slots__ = ("_anchor_epoch_nanos", "_anchor_mono_nanos")

    def __init__(
        self, anchor_epoch_nanos: int | None = None, anchor_mono_nanos: int | None = None
    ) -> None:
        """Anchors at the given pair, or (both omitted) at the current wall and monotonic clocks."""
        if (anchor_epoch_nanos is None) != (anchor_mono_nanos is None):
            raise ValueError("give both anchor readings or neither")
        if anchor_epoch_nanos is None or anchor_mono_nanos is None:
            anchor_epoch_nanos = time.time_ns()
            anchor_mono_nanos = time.perf_counter_ns()
        self._anchor_epoch_nanos = anchor_epoch_nanos
        self._anchor_mono_nanos = anchor_mono_nanos

    def epoch_nanos(self, event_nanos: int) -> int:
        """Returns the Unix-epoch nanoseconds for a monotonic reading from this process."""
        return self._anchor_epoch_nanos + (event_nanos - self._anchor_mono_nanos)
