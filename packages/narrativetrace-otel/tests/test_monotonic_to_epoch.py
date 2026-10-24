# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-167: the monotonic-to-epoch anchor, mirroring Java's MonotonicToEpochTest."""

from __future__ import annotations

import time

import pytest
from narrativetrace_otel.monotonic_to_epoch import MonotonicToEpoch

ANCHOR_EPOCH = 1_700_000_000_000_000_000
ANCHOR_MONO = 5_000


def test_a_reading_after_the_anchor_lands_after_the_anchor_epoch() -> None:
    clock = MonotonicToEpoch(ANCHOR_EPOCH, ANCHOR_MONO)
    assert clock.epoch_nanos(ANCHOR_MONO + 250) == ANCHOR_EPOCH + 250


def test_the_anchor_reading_maps_to_the_anchor_epoch() -> None:
    assert MonotonicToEpoch(ANCHOR_EPOCH, ANCHOR_MONO).epoch_nanos(ANCHOR_MONO) == ANCHOR_EPOCH


def test_a_reading_before_the_anchor_lands_before_the_anchor_epoch() -> None:
    clock = MonotonicToEpoch(ANCHOR_EPOCH, ANCHOR_MONO)
    assert clock.epoch_nanos(ANCHOR_MONO - 100) == ANCHOR_EPOCH - 100


def test_the_default_anchor_tracks_the_wall_clock() -> None:
    clock = MonotonicToEpoch()
    assert abs(clock.epoch_nanos(time.perf_counter_ns()) - time.time_ns()) < 60_000_000_000


def test_a_half_given_anchor_is_refused() -> None:
    with pytest.raises(ValueError, match="both anchor readings or neither"):
        MonotonicToEpoch(ANCHOR_EPOCH)
