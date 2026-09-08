# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Concurrency metadata attached to nodes participating in a concurrent group.

``ConcurrencyKind`` and ``ConcurrencyInfo``. Renderers use this to group related
nodes and explain whether work was awaited (fork/join) or launched in the background
(fire-and-forget).

Python divergence (see plan PY7 / core-pipeline §TS-CORE-6): Java's thread-identity fields are
kept for the ``ThreadPoolExecutor`` substrate, and an optional ``task_label`` is added for the
asyncio substrate where thread identity is meaningless.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum


class ConcurrencyKind(Enum):
    """Relationship between concurrent work and the launching call."""

    FORK_JOIN = "fork_join"
    """Concurrent work that is later joined back into the parent flow."""

    FIRE_AND_FORGET = "fire_and_forget"
    """Background work launched from the parent without a join step."""

    ASYNC = "async"
    """Work a worker picked up under a propagated snapshot, keyed by the launching span.

    Additive, and set at the async boundary only — the first span a thread or task opens under an
    activated snapshot. Everything deeper is ordinary sequential work on that worker. Without it a
    structural artifact pins the scheduler's dispatch order, and no concurrent scenario can hold a
    stable baseline.
    """


@dataclass(frozen=True, slots=True)
class ConcurrencyInfo:
    """Stable group identity plus substrate metadata for one concurrent node."""

    group_id: str
    kind: ConcurrencyKind
    thread_name: str | None = None
    thread_id: int = 0
    virtual: bool = False
    task_label: str | None = None


@dataclass(frozen=True, slots=True)
class ThreadIdentity:
    """Which thread executed one call — canonical schema 1.2 ``thread.name`` / ``thread.id``.

    Recorded per entry, unlike :class:`ConcurrencyInfo`, which exists only for nodes belonging to a
    concurrent group. A trace that fans work out over a pool is unreadable without it: two sibling
    subtrees look interleaved until you can see they ran on different threads.

    ``virtual`` is always ``False`` here. CPython has no virtual-thread analogue, so the honest
    answer for a captured entry is "not virtual"; the schema's ``null`` means "thread identity was
    not captured at all", which is a different statement.
    """

    name: str
    thread_id: int
    virtual: bool = False

    @classmethod
    def current(cls) -> ThreadIdentity:
        """Reads the identity of the calling thread."""
        thread = threading.current_thread()
        return cls(thread.name, thread.ident if thread.ident is not None else 0)
