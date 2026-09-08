# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Fork-join and fire-and-forget concurrency groups over asyncio and threads.

``ForkGroup`` / ``FireAndForgetGroup`` / ``ConcurrencySupport``. A group wraps each
concurrent task so it runs inside an *activated snapshot* — a fresh child stack that inherits the
parent's trace id, service identity, config level, AND request/user metadata (full-identity
propagation, which two sibling runtimes initially missed). Collected child roots are grafted back
under the parent span, tagged with :class:`ConcurrencyInfo`.

Both helpers activate with
:meth:`~narrativetrace.context.ContextSnapshot.activate_without_adoption`: they publish their own
children — the fork under its parent span at ``merge()``, the background work behind a launcher
marker through ``child_roots()`` — so a snapshot that also handed those spans back to the
launching stack would show every member twice.

Works over ``asyncio.gather`` / ``TaskGroup`` (``wrap_async``) and ``ThreadPoolExecutor``
(``wrap``); the snapshot carries the needed state, so no explicit ``copy_context`` is required.
"""

from __future__ import annotations

import itertools
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import TypeVar

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.context import NarrativeContext
from narrativetrace.ids import SpanId
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature

_T = TypeVar("_T")

_FORK_COUNTER = itertools.count(1)
_FANF_COUNTER = itertools.count(1)


def _derive_label(roots: list[TraceNode]) -> str | None:
    if not roots:
        return None
    sig = roots[0].signature
    return f"{sig.class_name}.{sig.method_name}"


@dataclass(slots=True)
class _CollectedChild:
    roots: list[TraceNode]
    thread_name: str | None


class ForkJoinGroup:
    """Fork-join concurrency helper: wrap tasks, then :meth:`merge` under the parent span."""

    def __init__(
        self, context: NarrativeContext, group_id: str, parent_span_id: SpanId | None
    ) -> None:
        self._context = context
        self._group_id = group_id
        self._parent_span_id = parent_span_id
        self._children: list[_CollectedChild] = []
        self._lock = threading.Lock()

    @classmethod
    def create(cls, context: NarrativeContext) -> ForkJoinGroup:
        group = cls(context, f"fork-{next(_FORK_COUNTER)}", context.current_span_id())
        context.on_fork_created(group._group_id)
        return group

    @property
    def group_id(self) -> str:
        return self._group_id

    def wrap(self, task: Callable[[], _T]) -> Callable[[], _T]:
        """Wraps a synchronous task for a ThreadPoolExecutor; captures its subtree on completion."""
        snapshot = self._context.snapshot()

        def wrapped() -> _T:
            with snapshot.activate_without_adoption():
                try:
                    return task()
                finally:
                    self._collect(threading.current_thread().name)

        return wrapped

    async def run_async(self, thunk: Callable[[], Awaitable[_T]]) -> _T:
        """Runs a coroutine thunk inside the group's snapshot; captures its subtree on completion.

        ``thunk`` must *create* the awaitable (so the traced ``enter`` happens inside the activated
        snapshot), e.g. ``group.run_async(lambda: service.charge(order))``.
        """
        snapshot = self._context.snapshot()
        with snapshot.activate_without_adoption():
            try:
                return await thunk()
            finally:
                self._collect(None)

    def _collect(self, thread_name: str | None) -> None:
        roots = self._context.capture_local_trace().roots
        self._context.clear_local_trace()
        if roots:
            with self._lock:
                self._children.append(_CollectedChild(roots, thread_name))

    def merge(self) -> list[TraceNode]:
        """Grafts collected child subtrees under the parent span, tagged with concurrency info."""
        with self._lock:
            collected = list(self._children)
            self._children.clear()
        merged: list[TraceNode] = []
        for child in collected:
            info = ConcurrencyInfo(
                self._group_id,
                ConcurrencyKind.FORK_JOIN,
                thread_name=child.thread_name,
                task_label=_derive_label(child.roots),
            )
            for root in child.roots:
                tagged = replace(root, concurrency=info)
                self._context.emit_trace_node(tagged, self._parent_span_id)
                merged.append(tagged)
        self._context.on_merge(self._group_id, merged)
        return merged


class FireAndForgetGroup:
    """Background-work helper: a launcher marker is grafted at create time (no merge step)."""

    def __init__(self, context: NarrativeContext, group_id: str) -> None:
        self._context = context
        self._group_id = group_id
        self._collected: list[TraceNode] = []
        self._lock = threading.Lock()

    @classmethod
    def create(cls, context: NarrativeContext, launching_class_name: str) -> FireAndForgetGroup:
        group = cls(context, f"fanf-{next(_FANF_COUNTER)}")
        launcher = _create_launcher_node(group._group_id, launching_class_name)
        context.emit_trace_node(launcher, context.current_span_id())
        context.on_fire_and_forget_launched(group._group_id)
        return group

    @property
    def group_id(self) -> str:
        return self._group_id

    def wrap(self, task: Callable[[], _T]) -> Callable[[], _T]:
        """Wraps a synchronous background task; captures and tags its subtree on completion."""
        snapshot = self._context.snapshot()

        def wrapped() -> _T:
            with snapshot.activate_without_adoption():
                try:
                    return task()
                finally:
                    self._collect_and_tag(threading.current_thread().name)

        return wrapped

    async def run_async(self, thunk: Callable[[], Awaitable[_T]]) -> _T:
        """Runs a background coroutine thunk inside the group's snapshot (see ForkJoinGroup)."""
        snapshot = self._context.snapshot()
        with snapshot.activate_without_adoption():
            try:
                return await thunk()
            finally:
                self._collect_and_tag(None)

    def child_roots(self) -> list[TraceNode]:
        """The collected background subtrees, tagged with fire-and-forget concurrency info."""
        with self._lock:
            return list(self._collected)

    def _collect_and_tag(self, thread_name: str | None) -> None:
        roots = self._context.capture_local_trace().roots
        self._context.clear_local_trace()
        if not roots:
            return
        info = ConcurrencyInfo(
            self._group_id,
            ConcurrencyKind.FIRE_AND_FORGET,
            thread_name=thread_name,
            task_label=_derive_label(roots),
        )
        with self._lock:
            self._collected.extend(replace(root, concurrency=info) for root in roots)


def _create_launcher_node(group_id: str, class_name: str) -> TraceNode:
    signature = MethodSignature(class_name, "fire-and-forget", [])
    info = ConcurrencyInfo(
        group_id,
        ConcurrencyKind.FIRE_AND_FORGET,
        thread_name=threading.current_thread().name,
    )
    return TraceNode(signature, [], None, 0, 0, info)
