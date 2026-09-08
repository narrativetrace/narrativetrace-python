# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for PerishableMap eviction semantics."""

from __future__ import annotations

import pytest

from narrativetrace.pipeline.perishable import PerishableMap


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="max_capacity must be positive"):
        PerishableMap(0, 1.0, lambda _v: None)


def test_get_remove_size() -> None:
    m: PerishableMap[str, int] = PerishableMap(4, 100.0, lambda _v: None)
    m.put("a", 1)
    assert m.get("a") == 1
    assert m.size() == 1
    assert m.remove("a") == 1
    assert m.get("a") is None
    assert m.remove("missing") is None


def test_over_capacity_evicts_oldest_and_fires_callback() -> None:
    evicted: list[int] = []
    clock = _Clock()
    m: PerishableMap[str, int] = PerishableMap(2, 100.0, evicted.append, clock)
    clock.now = 1
    m.put("a", 1)
    clock.now = 2
    m.put("b", 2)
    clock.now = 3
    m.put("c", 3)  # capacity 2 → evict oldest "a"
    assert evicted == [1]
    assert m.get("a") is None
    assert {m.get("b"), m.get("c")} == {2, 3}


def test_reput_at_capacity_evicts_nothing() -> None:
    evicted: list[int] = []
    clock = _Clock()
    m: PerishableMap[str, int] = PerishableMap(2, 100.0, evicted.append, clock)
    clock.now = 1
    m.put("a", 1)
    clock.now = 2
    m.put("b", 2)  # at capacity
    clock.now = 3
    m.put("a", 10)  # re-put existing key → no eviction (documented divergence from Java)
    assert evicted == []
    assert m.get("a") == 10
    assert m.get("b") == 2


def test_ttl_expiry_fires_callback() -> None:
    evicted: list[int] = []
    clock = _Clock()
    m: PerishableMap[str, int] = PerishableMap(10, 5.0, evicted.append, clock)
    clock.now = 0
    m.put("a", 1)
    clock.now = 10  # > ttl 5
    m.put("b", 2)  # put triggers expiry sweep
    assert evicted == [1]
    assert m.get("a") is None
    assert m.get("b") == 2
