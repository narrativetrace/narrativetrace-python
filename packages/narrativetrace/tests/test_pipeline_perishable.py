# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for PerishableMap eviction semantics."""

from __future__ import annotations

import itertools
import sys
import threading
import time

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


def _expired_pair(
    on_evict: object,
) -> tuple[PerishableMap[str, str], _Clock]:
    """A map holding two entries, both past their TTL at ``clock.now == 10``."""
    clock = _Clock()
    m: PerishableMap[str, str] = PerishableMap(8, 1.0, on_evict, clock)  # type: ignore[arg-type]
    clock.now = 0
    m.put("a", "a-old")
    m.put("b", "b-old")
    clock.now = 10
    return m, clock


def test_a_replacement_put_by_a_callback_survives_the_sweep() -> None:
    """B-169: the sweep removed whatever sat under an expired key, so a replacement put under
    that key while the callbacks ran (the OTel listener starting a span) was evicted and ended
    as orphaned."""
    evicted: list[str] = []
    holder: list[PerishableMap[str, str]] = []

    def on_evict(value: str) -> None:
        evicted.append(value)
        if value == "a-old":
            holder[0].put("b", "b-fresh")

    m, _ = _expired_pair(on_evict)
    holder.append(m)
    m.put("c", "c")

    assert m.get("b") == "b-fresh"
    assert evicted == ["a-old", "b-old"]


def test_a_callback_removing_another_expired_entry_neither_raises_nor_calls_back_twice() -> None:
    """Owner ruling (b): an entry already being evicted is no longer in the map, so a callback's
    ``remove`` of it answers ``None`` and the entry is called back exactly once."""
    evicted: list[str] = []
    removed: list[str | None] = []
    holder: list[PerishableMap[str, str]] = []

    def on_evict(value: str) -> None:
        evicted.append(value)
        if value == "a-old":
            removed.append(holder[0].remove("b"))

    m, _ = _expired_pair(on_evict)
    holder.append(m)
    m.put("c", "c")

    assert removed == [None]
    assert evicted == ["a-old", "b-old"]


def test_a_callback_removing_its_own_key_gets_none() -> None:
    removed: list[str | None] = []
    holder: list[PerishableMap[str, str]] = []

    def on_evict(value: str) -> None:
        removed.append(holder[0].remove("a" if value == "a-old" else "b"))

    m, _ = _expired_pair(on_evict)
    holder.append(m)
    m.put("c", "c")

    assert removed == [None, None]


def _hammer(
    m: PerishableMap[int, int],
    seed: int,
    barrier: threading.Barrier,
    deadline: float,
    failures: list[BaseException],
) -> None:
    try:
        barrier.wait(timeout=5)
        i = 0
        while time.monotonic() < deadline and i < 50_000:
            key = (seed * 7 + i) % 24
            if i % 3 == 0:
                m.remove(key)
            else:
                m.put(key, i)
            m.get(key)
            i += 1
    except BaseException as error:  # the test reports any failure
        failures.append(error)


def test_concurrent_puts_and_removes_while_entries_expire_raise_nothing() -> None:
    ticks = itertools.count()
    callbacks: list[int] = []
    m: PerishableMap[int, int] = PerishableMap(
        8, 20.0, callbacks.append, lambda: float(next(ticks))
    )
    workers = 6
    barrier = threading.Barrier(workers)
    failures: list[BaseException] = []
    deadline = time.monotonic() + 2.0
    threads = [
        threading.Thread(target=_hammer, args=(m, n, barrier, deadline, failures))
        for n in range(workers)
    ]
    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        sys.setswitchinterval(previous_interval)

    assert failures == []
    assert m.size() <= 8
