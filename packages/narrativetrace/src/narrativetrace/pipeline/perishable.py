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

import time
from collections.abc import Callable
from dataclasses import dataclass

_DEFAULT_CLOCK = time.monotonic


@dataclass(slots=True)
class _TimedEntry[V]:
    value: V
    created: float


class PerishableMap[K, V]:
    """A capacity- and TTL-bounded map with an eviction callback."""

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
        self._entries: dict[K, _TimedEntry[V]] = {}

    def put(self, key: K, value: V) -> None:
        """Inserts/overwrites, evicting expired (and, for new keys only, over-capacity) first."""
        self._evict_expired()
        if key not in self._entries:  # divergence: overwrite at capacity evicts nothing
            self._evict_over_capacity()
        self._entries[key] = _TimedEntry(value, self._clock())

    def get(self, key: K) -> V | None:
        """Returns the value for ``key`` or ``None``."""
        entry = self._entries.get(key)
        return entry.value if entry is not None else None

    def remove(self, key: K) -> V | None:
        """Removes and returns the value for ``key`` or ``None``."""
        entry = self._entries.pop(key, None)
        return entry.value if entry is not None else None

    def size(self) -> int:
        """Number of entries currently held."""
        return len(self._entries)

    def _evict_expired(self) -> None:
        now = self._clock()
        expired = [k for k, e in self._entries.items() if now - e.created > self._ttl]
        for key in expired:
            entry = self._entries.pop(key)
            self._on_evict(entry.value)

    def _evict_over_capacity(self) -> None:
        while len(self._entries) >= self._max_capacity:
            oldest = self._find_oldest()
            if oldest is None:
                break
            entry = self._entries.pop(oldest)
            self._on_evict(entry.value)

    def _find_oldest(self) -> K | None:
        oldest_key: K | None = None
        oldest_time = float("inf")
        for key, entry in self._entries.items():
            if entry.created < oldest_time:
                oldest_time = entry.created
                oldest_key = key
        return oldest_key
