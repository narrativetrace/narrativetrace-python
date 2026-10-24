# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Bounded map with TTL-based and capacity-based eviction.

``PerishableMap`` (used by the OTel consumer, PY10, to hold active spans awaiting
completion). Eviction is lazy — it happens on :meth:`put`, not on a background timer. Evicted
values are passed to an ``on_evict`` callback so callers can clean up (e.g. ending orphaned
spans).

**Documented divergence (plan decision point 5 / core-pipeline §TS-PIPE-9):** re-putting an
existing key at capacity evicts *nothing* (Java evicts the oldest other entry). This matches the
pinned .NET/TS semantics and is the more predictable contract.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

_DEFAULT_CLOCK = time.monotonic


@dataclass(slots=True, eq=False)
class _TimedEntry[V]:
    """Compared by identity: a replacement entry never equals the one it replaced."""

    value: V
    created: float


class PerishableMap[K, V]:
    """A capacity- and TTL-bounded map with an eviction callback.

    Thread-safe (B-169): an :class:`~threading.RLock` guards every read-modify-write, because the
    OTel listener puts and removes on caller threads. A sweep removes exactly the entry it
    examined (by identity), so a replacement put under an expired key is never evicted in its
    place, and an entry is called back only when its own removal won -- never twice. Callbacks run
    *after* the lock is released (collect under the lock, release, then call): a callback that
    re-enters the map cannot deadlock and never observes a half-finished sweep. By then every
    evicted entry is already out of the map, so a callback's ``remove`` of one answers ``None``.
    """

    def __init__(
        self,
        max_capacity: int,
        ttl_seconds: float,
        on_evict: Callable[[V], None],
        clock: Callable[[], float] = _DEFAULT_CLOCK,
    ) -> None:
        if max_capacity < 1:
            raise ValueError(f"max_capacity must be positive, got {max_capacity}")
        self._max_capacity = max_capacity
        self._ttl = ttl_seconds
        self._on_evict = on_evict
        self._clock = clock
        self._lock = threading.RLock()
        self._entries: dict[K, _TimedEntry[V]] = {}

    def put(self, key: K, value: V) -> None:
        """Inserts/overwrites, evicting expired (and, for new keys only, over-capacity) first."""
        with self._lock:
            evicted = self._evict_expired()
            if key not in self._entries:  # divergence: overwrite at capacity evicts nothing
                evicted += self._evict_over_capacity()
            self._entries[key] = _TimedEntry(value, self._clock())
        for entry in evicted:
            self._on_evict(entry.value)

    def get(self, key: K) -> V | None:
        """Returns the value for ``key`` or ``None``."""
        with self._lock:
            entry = self._entries.get(key)
            return entry.value if entry is not None else None

    def remove(self, key: K) -> V | None:
        """Removes and returns the value for ``key`` or ``None``."""
        with self._lock:
            entry = self._entries.pop(key, None)
            return entry.value if entry is not None else None

    def size(self) -> int:
        """Number of entries currently held."""
        with self._lock:
            return len(self._entries)

    def _evict_expired(self) -> list[_TimedEntry[V]]:
        """Removes the expired entries; the caller (holding the lock) calls back afterwards."""
        now = self._clock()
        evicted: list[_TimedEntry[V]] = []
        for key, examined in list(self._entries.items()):
            if now - examined.created > self._ttl and self._entries.get(key) is examined:
                del self._entries[key]
                evicted.append(examined)
        return evicted

    def _evict_over_capacity(self) -> list[_TimedEntry[V]]:
        evicted: list[_TimedEntry[V]] = []
        while len(self._entries) >= self._max_capacity:
            oldest = self._find_oldest()
            if oldest is None:
                break
            evicted.append(self._entries.pop(oldest))
        return evicted

    def _find_oldest(self) -> K | None:
        oldest_key: K | None = None
        oldest_time = float("inf")
        for key, entry in self._entries.items():
            if entry.created < oldest_time:
                oldest_time = entry.created
                oldest_key = key
        return oldest_key
