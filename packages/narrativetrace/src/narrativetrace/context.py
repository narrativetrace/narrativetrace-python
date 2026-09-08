# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Capture API: the NarrativeContext contract, a contextvars-backed implementation, and no-op.

``NarrativeContext`` / ``ThreadLocalNarrativeContext`` / ``ContextSnapshot`` /
``NoopNarrativeContext``. The Java ``ThreadLocal`` per-thread stack becomes a
:class:`contextvars.ContextVar` per context instance — isolating both threads *and* asyncio
tasks (a fresh thread and a freshly-created task each lazily get their own stack).

Key contracts pinned here (see core-pipeline §TS-CORE-3/4):

* ``is_active`` / ``captures_parameter_values`` are performance hints checked *before* rendering.
* ``reset()`` is request-scoped: it removes only the caller's own span ids from the shared
  store, so concurrent in-flight requests are unaffected.
"""

from __future__ import annotations

import contextvars
import threading
import time
import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, replace
from typing import TypeVar

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind, ThreadIdentity
from narrativetrace.events import (
    EnterEvent,
    ExitEvent,
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
    span_id_of,
)
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel
from narrativetrace.loss import TraceLoss
from narrativetrace.metadata import (
    ClientIp,
    EnduserId,
    HttpRoute,
    ServiceIdentity,
    SessionId,
    TenantId,
)
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.pipeline.event_store import EventStore
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree, build_trace_tree
from narrativetrace.tree_walk import TreeWalk
from narrativetrace.values import RenderedValue

_T = TypeVar("_T")


def _now_nanos() -> int:
    return time.perf_counter_ns()


# --------------------------------------------------------------------------- #
# Contracts                                                                    #
# --------------------------------------------------------------------------- #
class ContextSnapshot(ABC):
    """A captured trace continuation that can be activated on another thread/task."""

    @abstractmethod
    def activate(self) -> AbstractContextManager[None]:
        """Activates this snapshot; the returned context manager restores prior state on exit."""

    def activate_without_adoption(self) -> AbstractContextManager[None]:
        """Activates without handing the work back: the caller reports its children itself.

        INTENT: For helpers that own their children's presentation —
        :meth:`~narrativetrace.groups.ForkJoinGroup.merge` re-emits them under the fork's parent
        span, :class:`~narrativetrace.groups.FireAndForgetGroup` hands them out through
        ``child_roots()`` behind a launcher marker. Handing them over as well would show the same
        work twice, or make a parent's tree depend on when a detached child happened to finish.

        Ordinary propagation — a task decorator, a manual snapshot around a thread or task — wants
        :meth:`activate`: async work belongs to the trace that launched it.
        """
        return self.activate()

    def wrap(self, task: Callable[[], _T]) -> Callable[[], _T]:
        """Wraps a callable so it activates this snapshot for the duration of the call."""

        def wrapped() -> _T:
            with self.activate():
                return task()

        return wrapped


class NarrativeContext(ABC):
    """Central capture API used by instrumentation to record traced method lifecycles."""

    # -- performance hints -------------------------------------------------- #
    def is_active(self) -> bool:
        """Whether this context is actively recording (``False`` → skip capture entirely)."""
        return True

    def captures_parameter_values(self) -> bool:
        """Whether captured parameter values are retained at the current level."""
        return True

    # -- lifecycle (required) ---------------------------------------------- #
    @abstractmethod
    def enter_method(self, signature: MethodSignature) -> SpanId | None:
        """Records entry into a method, returning its span id (or ``None`` when disabled)."""

    @abstractmethod
    def exit_method_with_return(
        self,
        rendered_return_value: str | None,
        structured_return_value: RenderedValue | None = None,
        span_id: SpanId | None = None,
    ) -> None:
        """Records a normal return, optionally for a specific detached frame."""

    @abstractmethod
    def exit_method_with_exception(
        self,
        exception: BaseException,
        error_context: str | None = None,
        span_id: SpanId | None = None,
    ) -> None:
        """Records an exceptional exit, optionally for a specific detached frame."""

    @abstractmethod
    def capture_trace(self) -> TraceTree:
        """Returns the immutable trace tree accumulated since the last ``reset()``."""

    @abstractmethod
    def reset(self) -> None:
        """Clears the caller's own accumulated trace state."""

    @abstractmethod
    def snapshot(self) -> ContextSnapshot:
        """Creates a snapshot for cross-thread/task trace propagation."""

    # -- optional overrides ------------------------------------------------- #
    def detach_frame(self, span_id: SpanId) -> None:
        """Detaches a frame from the active stack without completing it."""

    def capture_local_trace(self) -> TraceTree:
        """Trace tree visible from the current scope (defaults to :meth:`capture_trace`)."""
        return self.capture_trace()

    def clear_local_trace(self) -> None:
        """Purges the current scope's own events once a caller has copied them elsewhere.

        Default no-op for contexts with nothing to purge. A fork/fire-and-forget helper calls this
        immediately after :meth:`capture_local_trace` so a worker's raw events do not outlive the
        copied :class:`~narrativetrace.nodes.TraceNode`\\ s made from them (a bug-hunt finding).
        """

    def trace_loss(self) -> TraceLoss:
        """What this scope's trace is missing: shed events, and async scopes the cap refused.

        :meth:`TraceLoss.none` unless a best-effort path lost something. Take a reading before a
        scenario and :meth:`TraceLoss.since` after it to attribute loss to that scenario, since
        the counters only grow.
        """
        return TraceLoss.none()

    def begin_scope(self, span_id: SpanId) -> SpanId | None:
        """Sets the scoped parent; returns the previous scope for restoration."""
        return None

    def end_scope(self, previous_scope: SpanId | None) -> None:
        """Restores the scoped parent to a previous value."""

    def run_scoped(self, span_id: SpanId, fn: Callable[[], _T]) -> _T:
        """Runs ``fn`` with ``span_id`` as the scoped parent."""
        previous = self.begin_scope(span_id)
        try:
            return fn()
        finally:
            self.end_scope(previous)

    def current_span_id(self) -> SpanId | None:
        """Span id of the currently executing traced call, or ``None`` outside any trace.

        Resolved the way span creation resolves a parent: the scoped (async) parent first —
        an ``async`` traced method registers through :meth:`begin_scope` and never sits on the
        active stack — then the top of the active stack, then a propagated snapshot's parent.
        """
        return None

    def emit_trace_node(self, node: TraceNode, parent_span_id: SpanId | None) -> None:
        """Replays a pre-built node as enter/exit event pairs into the event trail."""

    def on_fork_created(self, group_id: str) -> None:
        """Lifecycle callback fired when a fork group is created."""

    def on_merge(self, group_id: str, members: list[TraceNode]) -> None:
        """Lifecycle callback fired when a fork group merges its children."""

    def on_fire_and_forget_launched(self, group_id: str) -> None:
        """Lifecycle callback fired when a fire-and-forget group is launched."""

    def set_request_context(
        self, http_method: str | None, http_route: HttpRoute | None, client_ip: ClientIp | None
    ) -> None:
        """Sets request-scoped fields stamped onto subsequently created spans."""

    def set_user_context(
        self,
        enduser_id: EnduserId | None,
        session_id: SessionId | None,
        tenant_id: TenantId | None,
    ) -> None:
        """Sets user identity fields stamped onto subsequently created spans."""

    def trace_id(self) -> TraceId:
        """Returns the current trace id, generating one eagerly if absent."""
        return TraceId.generate()

    def adopt_trace_id(self, trace_id: TraceId) -> None:
        """Adopts an inbound (e.g. W3C ``traceparent``) trace id for the current scope."""

    def story_id(self) -> str | None:
        """Story id derived from the first root-level call, or ``None``."""
        return None

    def chapter_id(self) -> str | None:
        """Chapter id for this service's contribution to the story, or ``None``."""
        return None


# --------------------------------------------------------------------------- #
# Request metadata + per-execution stack                                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _RequestMetadata:
    http_method: str | None = None
    http_route: HttpRoute | None = None
    client_ip: ClientIp | None = None
    enduser_id: EnduserId | None = None
    session_id: SessionId | None = None
    tenant_id: TenantId | None = None

    def with_request(
        self, http_method: str | None, http_route: HttpRoute | None, client_ip: ClientIp | None
    ) -> _RequestMetadata:
        return replace(self, http_method=http_method, http_route=http_route, client_ip=client_ip)

    def with_user(
        self,
        enduser_id: EnduserId | None,
        session_id: SessionId | None,
        tenant_id: TenantId | None,
    ) -> _RequestMetadata:
        return replace(self, enduser_id=enduser_id, session_id=session_id, tenant_id=tenant_id)


_EMPTY_METADATA = _RequestMetadata()

MAX_ADOPTED_SPANS = 10_000
"""Ceiling on spans one stack accepts from worker scopes, and on its live-child registrations.

A request-scoped stack is dropped whole by ``reset()``, so the bound is not about that memory. It
exists for the execution context that never resets — a daemon loop dispatching async work for the
life of the process — where an unbounded set is a genuine leak. Same value in every runtime.
"""


@dataclass(slots=True, weakref_slot=True, eq=False)
class _TraceStack:
    """Per-execution-context capture state (Java's thread-local ``TraceStack``).

    Identity-compared (``eq=False``): a stack *is* one execution's state, never a value, and the
    live-child registry keys weak references by it.

    ``known`` is written by the owning execution context and read by an origin stack while the
    owner is still running. That is safe without a lock — ``set.add`` and copying a set are both
    atomic in CPython — while the registry and the adopted set, whose updates are check-then-act,
    are guarded by :attr:`lock`.
    """

    active: list[SpanId] = field(default_factory=list)
    known: set[SpanId] = field(default_factory=set)
    trace_id: TraceId | None = None
    scoped_parent: SpanId | None = None
    snapshot_parent: SpanId | None = None
    story_id: str | None = None
    chapter_id: str | None = None
    metadata: _RequestMetadata = _EMPTY_METADATA
    from_snapshot: bool = False
    adopted: set[SpanId] = field(default_factory=set)
    live_children: set[weakref.ref[_TraceStack]] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    max_adopted_spans: int = MAX_ADOPTED_SPANS
    refused_scopes: int = 0
    refused_spans: int = 0
    closed: bool = False
    pending_snapshots: int = 0

    # -- published, therefore reportable ------------------------------------ #
    def adopt(self, span_ids: set[SpanId]) -> int:
        """Takes over the spans a worker published under a snapshot of this stack.

        Called from the worker's execution context at scope close, so the update is locked.

        All-or-nothing: a batch that would cross :attr:`max_adopted_spans` is refused whole and
        counted. Adopting a prefix of it would strand children whose parent stayed out, and a
        parentless node is promoted to a root — so the artifact would assert a call graph that
        never happened, differently on every run, since a batch arrives as an unordered set. An
        incomplete trace is honest; a wrong-shaped one is not.

        Returns how many spans were discarded because this stack was already :attr:`closed` (its
        owning request already reset) — a bug-hunt finding: a *closed*-lifecycle check, not a
        garbage-collection one. A weakref-liveness check alone is unreliable (an object can outlive
        the request that reset it for an arbitrary, timing-dependent stretch under refcounting or a
        cyclic collector), so a late-arriving batch must be recognised and discarded explicitly
        rather than silently merged into an ``adopted`` set nothing will ever read again.
        """
        if not span_ids:
            return 0
        with self.lock:
            if self.closed:
                return len(span_ids)
            if len(self.adopted) + len(span_ids) > self.max_adopted_spans:
                self.refused_scopes += 1
                self.refused_spans += len(span_ids)
                return 0
            self.adopted.update(span_ids)
            return 0

    def close_and_collect(self) -> set[SpanId]:
        """Marks this stack closed (no further adoption accepted) and returns everything it owns
        right now: its own spans plus whatever it had already adopted from finished children.

        Deliberately excludes :meth:`live_child_span_ids`: a live child is still running elsewhere
        and will hand its spans over later, through :meth:`adopt` — which, on a now-closed stack,
        discards and counts them instead (a bug-hunt finding) rather than waiting for or reaching
        into a child that has not finished yet.
        """
        with self.lock:
            self.closed = True
            return set(self.known) | set(self.adopted)

    def has_pending_snapshots(self) -> bool:
        """Whether any :meth:`~ContextVarNarrativeContext.snapshot` taken from this stack has not
        yet been resolved (activated to completion, or never activated at all).

        A bug-hunt finding's real difficulty: a snapshot's origin reference is weak by design (an
        abandoned, never-activated snapshot must not keep a finished stack alive forever), but a
        weak reference can just as easily die *before* a snapshot that IS going to be used gets
        around to dereferencing it — CPython's refcounting collects this stack the instant nothing
        else holds it, which can be immediately after :meth:`close_and_collect` returns, regardless
        of whether a worker is still going to need it. This flag is what lets the owning context
        decide to hold this stack alive a while longer instead: strongly, but only for as long as
        outstanding snapshots exist, not indefinitely.
        """
        with self.lock:
            return self.pending_snapshots > 0

    def mark_snapshot_taken(self) -> None:
        """Records that one more snapshot now exists with this stack as its origin."""
        with self.lock:
            self.pending_snapshots += 1

    def mark_snapshot_resolved(self) -> bool:
        """Records that one snapshot has been activated to completion (or discarded unused).

        Returns whether this stack is both closed and free of every other outstanding snapshot —
        the owning context's cue to stop retaining it strongly.
        """
        with self.lock:
            self.pending_snapshots -= 1
            return self.closed and self.pending_snapshots <= 0

    def register_live_child(self, child: _TraceStack) -> weakref.ref[_TraceStack] | None:
        """Publishes a worker's stack to this one for the lifetime of its scope.

        Announced *before* the worker can publish a span, so this stack reports the worker's calls
        from the moment they exist rather than from the moment its scope closes — a framework
        routinely hands control back to the caller in between.

        Held weakly: a worker that dies mid-scope must not be kept alive by the registry, and its
        cleared registration simply contributes nothing.

        Bounded by the same ceiling as adoption, and for the same reason — the execution context
        that never resets. A refused registration loses nothing (the worker's spans still arrive
        through :meth:`adopt` at scope close, just later), so it is not counted as a refusal.

        Returns the handle to hand back to :meth:`unregister_live_child`, or ``None`` if refused.
        """
        if child is None:
            raise ValueError("Child stack is required")
        if child is self:
            raise ValueError("A stack cannot be its own live child")
        registration = weakref.ref(child)
        with self.lock:
            if len(self.live_children) >= self.max_adopted_spans:
                return None
            self.live_children.add(registration)
        return registration

    def unregister_live_child(self, registration: weakref.ref[_TraceStack] | None) -> None:
        """Ends a live registration. A ``None`` handle is one that was never made."""
        if registration is None:
            return
        with self.lock:
            self.live_children.discard(registration)

    def reportable_span_ids(self) -> set[SpanId]:
        """Everything this stack can answer for right now.

        Its own spans, the ones it has already adopted from finished children, and everything its
        live children can answer for. One definition serves both directions — a live child is read
        through it, and scope close hands exactly it over — so a call can never be visible while a
        scope is open and absent once it closes.
        """
        ids = set(self.known)
        ids |= self.adopted_span_ids()
        ids |= self.live_child_span_ids()
        return ids

    def adopted_span_ids(self) -> set[SpanId]:
        """A copy of the spans handed over by children whose scopes have closed."""
        with self.lock:
            return set(self.adopted)

    def live_child_span_ids(self) -> set[SpanId]:
        """What every live child can answer for, transitively.

        A chain of async hops reaches this stack whole rather than stopping at the first worker
        that dispatched further work. The mutual recursion with :meth:`reportable_span_ids` cannot
        cycle: a live child is always a stack freshly created by an activation and registered with
        exactly one origin, so the registry is a forest of new nodes with no back edge.

        Cleared registrations are pruned as they are found, so a worker that died without closing
        its scope does not hold its slot forever.
        """
        ids: set[SpanId] = set()
        for registration in self._live_child_registrations():
            child = registration()
            if child is None:
                self.unregister_live_child(registration)
            else:
                ids |= child.reportable_span_ids()
        return ids

    def _live_child_registrations(self) -> list[weakref.ref[_TraceStack]]:
        with self.lock:
            return list(self.live_children)

    def derive_story_id_if_absent(self, class_name: str, method_name: str) -> None:
        if not class_name:
            raise ValueError("Class name is required")
        if not method_name:
            raise ValueError("Method name is required")
        if self.story_id is None:
            self.story_id = f"{class_name}.{method_name}"
            self.chapter_id = self.story_id

    def peek_active(self) -> SpanId | None:
        return self.active[-1] if self.active else None

    def push_active(self, span_id: SpanId) -> None:
        self.active.append(span_id)
        self.known.add(span_id)

    def pop_active(self) -> SpanId:
        return self.active.pop()

    def detach(self, span_id: SpanId) -> None:
        if span_id in self.active:
            self.active.remove(span_id)

    @property
    def is_empty(self) -> bool:
        return not self.active


# --------------------------------------------------------------------------- #
# contextvars-backed implementation                                            #
# --------------------------------------------------------------------------- #
class ContextVarNarrativeContext(NarrativeContext):
    """Default context: a shared event store plus per-execution :class:`_TraceStack` state.

    The stack lives in a :class:`contextvars.ContextVar`, so a fresh thread and a freshly
    created asyncio task each lazily obtain their own isolated stack while sharing one store.
    """

    def __init__(
        self,
        config: NarrativeTraceConfig | None = None,
        service_identity: ServiceIdentity | None = None,
        store: EventStore | None = None,
    ) -> None:
        self._config = config if config is not None else NarrativeTraceConfig()
        self._service_identity = service_identity
        self._store = store if store is not None else EventStore()
        self._span_contexts: dict[SpanId, SpanContext] = {}
        self._span_lock = threading.Lock()
        self._stack_var: contextvars.ContextVar[_TraceStack | None] = contextvars.ContextVar(
            f"narrativetrace_stack_{id(self)}", default=None
        )
        self._discard_lock = threading.Lock()
        self._discarded_spans = 0
        self._retained_lock = threading.Lock()
        self._retained: set[_TraceStack] = set()

    @property
    def config(self) -> NarrativeTraceConfig:
        """The tracing configuration (its ``level`` may be changed at runtime)."""
        return self._config

    def _get_stack(self) -> _TraceStack:
        stack = self._stack_var.get()
        if stack is None:
            stack = _TraceStack()
            self._stack_var.set(stack)
        return stack

    # -- hints -------------------------------------------------------------- #
    def is_active(self) -> bool:
        return self._config.level.is_enabled(TracingLevel.ERRORS)

    def captures_parameter_values(self) -> bool:
        return self._config.level.is_enabled(TracingLevel.DETAIL)

    # -- enter -------------------------------------------------------------- #
    def enter_method(self, signature: MethodSignature) -> SpanId | None:
        if not self._config.level.is_enabled(TracingLevel.ERRORS):
            return None
        if not self._config.level.is_enabled(TracingLevel.DETAIL):
            signature = _suppress_parameter_values(signature)
        stack = self._get_stack()
        parent_span_id = self._resolve_parent_span_id(stack)
        if parent_span_id is None:
            stack.derive_story_id_if_absent(signature.class_name, signature.method_name)
        span_context = self._create_span_context(stack, parent_span_id)
        with self._span_lock:
            self._span_contexts[span_context.span_id] = span_context
        thread = ThreadIdentity.current()
        self._store.add(
            EnterEvent(span_context, _now_nanos(), signature, _async_tag_for(stack, thread), thread)
        )
        stack.push_active(span_context.span_id)
        return span_context.span_id

    def _resolve_parent_span_id(self, stack: _TraceStack) -> SpanId | None:
        if stack.scoped_parent is not None:
            return stack.scoped_parent
        active = stack.peek_active()
        if active is not None:
            return active
        return stack.snapshot_parent

    def _create_span_context(
        self, stack: _TraceStack, parent_span_id: SpanId | None
    ) -> SpanContext:
        trace_id = stack.trace_id
        if trace_id is None:
            trace_id = TraceId.generate()
            stack.trace_id = trace_id
        metadata = stack.metadata
        identity = self._service_identity
        return SpanContext(
            trace_id=trace_id,
            span_id=SpanId.generate(),
            parent_span_id=parent_span_id,
            http_method=metadata.http_method,
            http_route=metadata.http_route,
            client_ip=metadata.client_ip,
            enduser_id=metadata.enduser_id,
            session_id=metadata.session_id,
            tenant_id=metadata.tenant_id,
            story_id=stack.story_id,
            chapter_id=stack.chapter_id,
            service_name=identity.service_name if identity else None,
            service_version=identity.service_version if identity else None,
            environment=identity.environment if identity else None,
        )

    # -- scope -------------------------------------------------------------- #
    def begin_scope(self, span_id: SpanId) -> SpanId | None:
        stack = self._get_stack()
        previous = stack.scoped_parent
        stack.scoped_parent = span_id
        return previous

    def end_scope(self, previous_scope: SpanId | None) -> None:
        self._get_stack().scoped_parent = previous_scope

    def detach_frame(self, span_id: SpanId) -> None:
        self._get_stack().detach(span_id)

    def current_span_id(self) -> SpanId | None:
        # The same chain span creation uses (_resolve_parent_span_id): scoped parent
        # first, because an async traced method registers through begin_scope and
        # never sits on the active stack — peek_active alone answered None there,
        # and a fork/fire-and-forget group created inside a coroutine parented its
        # children as roots (2026-08-27 demo-tour defect, TestForkFromAsyncParent).
        return self._resolve_parent_span_id(self._get_stack())

    # -- exit --------------------------------------------------------------- #
    def exit_method_with_return(
        self,
        rendered_return_value: str | None,
        structured_return_value: RenderedValue | None = None,
        span_id: SpanId | None = None,
    ) -> None:
        outcome = Returned(rendered_return_value, structured_return_value)
        if span_id is None:
            self._exit_lifo(outcome, None)
            return
        self._append_exit(span_id, outcome, None)
        self._get_stack().detach(span_id)

    def exit_method_with_exception(
        self,
        exception: BaseException,
        error_context: str | None = None,
        span_id: SpanId | None = None,
    ) -> None:
        outcome = Threw(exception)
        if span_id is None:
            self._exit_lifo(outcome, error_context)
            return
        self._append_exit(span_id, outcome, error_context)
        self._get_stack().detach(span_id)

    def _exit_lifo(self, outcome: Returned | Threw, error_context: str | None) -> None:
        stack = self._get_stack()
        if stack.is_empty:
            return
        span_id = stack.pop_active()
        span_context = self._lookup_span(span_id)
        if span_context is None:
            return
        self._store.add(ExitEvent(span_context, _now_nanos(), outcome, error_context))

    def _append_exit(
        self, span_id: SpanId, outcome: Returned | Threw, error_context: str | None
    ) -> None:
        span_context = self._lookup_span(span_id)
        if span_context is None:
            return
        self._store.add(ExitEvent(span_context, _now_nanos(), outcome, error_context))

    def _lookup_span(self, span_id: SpanId) -> SpanContext | None:
        with self._span_lock:
            return self._span_contexts.get(span_id)

    # -- capture / reset ---------------------------------------------------- #
    def capture_trace(self) -> TraceTree:
        stack = self._get_stack()
        reportable = stack.reportable_span_ids()
        events = [e for e in self._store.events() if span_id_of(e) in reportable]
        # `stack.trace_id`, not `self.trace_id()`: reading the field never generates, so
        # capturing an idle context yields an empty tree with no identity attached to it.
        return build_trace_tree(events, self._config.level, stack.trace_id)

    def trace_loss(self) -> TraceLoss:
        stack = self._get_stack()
        with self._discard_lock:
            discarded = self._discarded_spans
        return TraceLoss(
            _dropped_events(self._store), stack.refused_scopes, stack.refused_spans, discarded
        )

    def reset(self) -> None:
        """Clears this scope's own state, INCLUDING spans already adopted from finished workers
        (a bug-hunt finding — an adopted worker subtree is this request's own reportable trace,
        so leaving it out of ``reset()`` while clearing everything else it owns is the same
        omission Java's fix closed). Marks the stack closed first, so any worker that finishes
        later hands its spans to a stack that recognises it can no longer take them (another
        bug-hunt finding).

        If a snapshot taken from this stack is still outstanding (activated-but-not-yet-resolved,
        or never activated at all), this stack is kept strongly reachable from the context until
        every one of them resolves — see :meth:`_ContextVarSnapshot._activate` for why a weak
        reference alone cannot be trusted to still be alive when that worker gets around to it.
        """
        stack = self._get_stack()
        self._purge_stack(stack)
        self._stack_var.set(None)
        if stack.has_pending_snapshots():
            with self._retained_lock:
                self._retained.add(stack)

    def clear_local_trace(self) -> None:
        """Purges the current scope's own events from the store once they have been collected
        elsewhere as copied :class:`~narrativetrace.nodes.TraceNode`\\ s (a bug-hunt finding: a
        fork/fire-and-forget helper's raw worker events must not outlive the copy it made of them,
        or they accumulate in the shared store for the rest of the process, invisible to every
        capture but never freed). Unlike :meth:`reset`, this does not detach the stack from its
        execution context — the caller is still running inside it.
        """
        self._purge_stack(self._get_stack())

    def _purge_stack(self, stack: _TraceStack) -> None:
        owned = stack.close_and_collect()
        if not owned:
            return
        with self._span_lock:
            for span_id in owned:
                self._span_contexts.pop(span_id, None)
        self._store.remove_spans(owned)

    def _record_discarded_spans(self, count: int) -> None:
        with self._discard_lock:
            self._discarded_spans += count

    def _release_resolved_snapshot(self, stack: _TraceStack) -> None:
        """Drops the strong hold :meth:`reset` may have placed on ``stack``, once its last
        outstanding snapshot has resolved. A no-op if it was never retained (the common case: no
        ``reset()`` raced this snapshot at all)."""
        if stack.mark_snapshot_resolved():
            with self._retained_lock:
                self._retained.discard(stack)

    # -- metadata / identity ----------------------------------------------- #
    def set_request_context(
        self, http_method: str | None, http_route: HttpRoute | None, client_ip: ClientIp | None
    ) -> None:
        stack = self._get_stack()
        stack.metadata = stack.metadata.with_request(http_method, http_route, client_ip)

    def set_user_context(
        self,
        enduser_id: EnduserId | None,
        session_id: SessionId | None,
        tenant_id: TenantId | None,
    ) -> None:
        stack = self._get_stack()
        stack.metadata = stack.metadata.with_user(enduser_id, session_id, tenant_id)

    def trace_id(self) -> TraceId:
        stack = self._get_stack()
        if stack.trace_id is None:
            stack.trace_id = TraceId.generate()
        return stack.trace_id

    def adopt_trace_id(self, trace_id: TraceId) -> None:
        self._get_stack().trace_id = trace_id

    def story_id(self) -> str | None:
        return self._get_stack().story_id

    def chapter_id(self) -> str | None:
        return self._get_stack().chapter_id

    # -- concurrency lifecycle --------------------------------------------- #
    def on_fork_created(self, group_id: str) -> None:
        self._store.add(ForkCreatedEvent(group_id, _now_nanos()))

    def on_merge(self, group_id: str, members: list[TraceNode]) -> None:
        self._store.add(MergeEvent(group_id, len(members), _now_nanos()))

    def on_fire_and_forget_launched(self, group_id: str) -> None:
        self._store.add(FireAndForgetEvent(group_id, _now_nanos()))

    def emit_trace_node(self, node: TraceNode, parent_span_id: SpanId | None) -> None:
        self._emit_trace_node(node, parent_span_id, TreeWalk())

    def _emit_trace_node(
        self, node: TraceNode, parent_span_id: SpanId | None, walk: TreeWalk
    ) -> None:
        """Publishes ``node`` and (bounded, cycle-safe) its descendants.

        Unlike a rendered artifact, unbounded recursion here hangs or crashes the *traced
        application itself*, not an output file -- this is a public API's own input
        (``NarrativeContext.emit_trace_node`` takes any ``TraceNode``), not a captured tree this
        runtime built and can trust.
        """
        stack = self._get_stack()
        span_context = self._create_span_context(stack, parent_span_id)
        with self._span_lock:
            self._span_contexts[span_context.span_id] = span_context
        enter = EnterEvent(span_context, node.start_time_nanos, node.signature, node.concurrency)
        exit_timestamp = node.start_time_nanos + node.duration_nanos
        stack.push_active(span_context.span_id)
        self._store.add(enter)
        if walk.stop_reason(node) is None:
            walk.enter(node)
            try:
                for child in node.children:
                    self._emit_trace_node(child, span_context.span_id, walk)
            finally:
                walk.exit(node)
        outcome = node.outcome if node.outcome is not None else Returned(None)
        self._store.add(
            ExitEvent(span_context, exit_timestamp, outcome, node.signature.error_context)
        )
        stack.detach(span_context.span_id)

    # -- snapshot ----------------------------------------------------------- #
    def snapshot(self) -> ContextSnapshot:
        stack = self._get_stack()
        stack.mark_snapshot_taken()
        return _ContextVarSnapshot(
            self, stack.trace_id, self._resolve_parent_span_id(stack), stack.metadata, stack
        )

    def _swap_stack(self, replacement: _TraceStack) -> contextvars.Token[_TraceStack | None]:
        """Installs ``replacement`` as this execution context's stack, returning the undo token."""
        return self._stack_var.set(replacement)

    def _restore_stack(self, token: contextvars.Token[_TraceStack | None]) -> None:
        self._stack_var.reset(token)


class _ContextVarSnapshot(ContextSnapshot):
    """A trace continuation plus a weak handle on the stack that took it.

    Weak by design: a snapshot handed to a queue must never keep a finished request's stack alive,
    and a stack that has been reset or collected simply adopts nothing.
    """

    def __init__(
        self,
        context: ContextVarNarrativeContext,
        trace_id: TraceId | None,
        parent_span_id: SpanId | None,
        metadata: _RequestMetadata,
        origin: _TraceStack,
    ) -> None:
        self._context = context
        self._trace_id = trace_id
        self._parent_span_id = parent_span_id
        self._metadata = metadata
        self._origin = weakref.ref(origin)

    def activate(self) -> AbstractContextManager[None]:
        return self._activate(adopt=True)

    def activate_without_adoption(self) -> AbstractContextManager[None]:
        return self._activate(adopt=False)

    @contextmanager
    def _activate(self, *, adopt: bool) -> Iterator[None]:
        """Runs the body on a fresh child stack, registered live and handed over at close.

        Registration comes first and unregistration last, with adoption in between: the two name
        the same set, so a capture racing this close sees the worker's calls through one side or
        the other, and never twice.

        ``adopt=False`` registers nothing and hands over nothing — its own grandchildren included,
        since they are only reachable through a stack the origin never learns about.

        A bug-hunt finding: a weak origin reference can die *before* a worker that is actually
        going to use it gets around to it — CPython's refcounting collects a stack the instant
        nothing else holds it, which can be immediately after its owner's ``reset()`` returns,
        regardless of whether some snapshot taken earlier is still going to need it. Checking
        ``origin.closed`` only means something if ``origin`` reliably resolves to the very object
        ``reset()`` marked, so :meth:`ContextVarNarrativeContext.snapshot` marks this stack pending
        at snapshot-creation time and :meth:`~ContextVarNarrativeContext.reset` keeps it strongly
        reachable for as long as any snapshot remains pending — this is what makes ``origin`` below
        reliable regardless of activation timing. A snapshot that is *never* activated keeps that
        one stack alive rather than nothing — the accepted cost of correctness over the weaker
        guarantee "usually collected soon" — but every *resolved* activation releases its share
        immediately, so the cost never compounds across requests.
        """
        origin = self._origin()
        child = _TraceStack(
            trace_id=self._trace_id,
            snapshot_parent=self._parent_span_id,
            metadata=self._metadata,
            from_snapshot=True,
        )
        registration = _register_live_child(origin, child) if adopt else None
        token = self._context._swap_stack(child)
        try:
            yield
        finally:
            self._context._restore_stack(token)
            if adopt:
                _adopt_into(self._context, origin, child)
                _unregister_live_child(origin, registration)
            if origin is not None:
                self._context._release_resolved_snapshot(origin)


def _async_tag_for(stack: _TraceStack, thread: ThreadIdentity) -> ConcurrencyInfo | None:
    """Tags the first span a worker opens under a propagated snapshot as concurrent work.

    Only that span: everything below it is ordinary sequential work on the same worker. The group
    is keyed by the launching span so every async child of one call renders as one group; work
    propagated with no parent span is keyed by the trace instead, since a parentless async root
    still needs a group to belong to.

    This is what lets a concurrent scenario hold a stable structural baseline — the scheduler
    decides which task starts first, so capture order is not behaviour and must not be asserted.
    """
    if not stack.from_snapshot or stack.peek_active() is not None:
        return None
    parent = stack.snapshot_parent
    key = parent.value if parent is not None else str(stack.trace_id)
    return ConcurrencyInfo(
        f"async-{key}",
        ConcurrencyKind.ASYNC,
        thread_name=thread.name,
        thread_id=thread.thread_id,
        virtual=thread.virtual,
    )


def _dropped_events(store: EventStore) -> int:
    """Reads a store's shed-event count, or zero from one that cannot shed.

    The default :class:`~narrativetrace.pipeline.event_store.EventStore` retains everything given
    to it; a store backed by the buffered consumer counts what backpressure cost. Asked for by
    duck-typing rather than by type, so a deployment can substitute either.
    """
    dropped_count = getattr(store, "dropped_count", None)
    return int(dropped_count()) if dropped_count is not None else 0


def _register_live_child(
    origin: _TraceStack | None, child: _TraceStack
) -> weakref.ref[_TraceStack] | None:
    """Announces the child stack to the origin, or does nothing when the origin is gone."""
    return None if origin is None else origin.register_live_child(child)


def _adopt_into(
    context: ContextVarNarrativeContext, origin: _TraceStack | None, child: _TraceStack
) -> None:
    """Hands the child's *reportable* set — not merely what it created — back to the origin.

    A worker that dispatched further async work has already adopted its own grandchildren, and a
    hand-over that dropped them would end the chain one hop from the origin, which is the only
    execution context anyone captures on.

    Skipped, with nothing counted or purged, when the origin is gone (garbage-collected): that is
    ambiguous, not evidence of loss — a worker that closed *before* this child did may already have
    handed the very same spans to its own origin, transitively, while the child was still live (a
    nested chain: origin → worker → grandchild, worker closes first). Purging here would delete
    events the origin's own ``capture_trace()`` still needs.

    A late worker whose origin is explicitly *closed* (reset while this worker was still
    registered as its live child — a bug-hunt finding) is unambiguous: the owning request ended,
    so there is no other path left for this data to reach anyone. Only that case discards and
    counts on the context — and "discarded" means gone from the shared store too, not merely
    uncredited to the
    origin, or the raw events would leak there forever just as uncounted as before the fix, only
    under a different name.
    """
    if origin is None:
        return
    reportable = child.reportable_span_ids()
    if not reportable:
        return
    discarded = origin.adopt(reportable)
    if discarded:
        context._record_discarded_spans(discarded)
        context._purge_stack(child)


def _unregister_live_child(
    origin: _TraceStack | None, registration: weakref.ref[_TraceStack] | None
) -> None:
    """Drops the live registration once adoption has taken the same spans over."""
    if origin is not None:
        origin.unregister_live_child(registration)


def _suppress_parameter_values(signature: MethodSignature) -> MethodSignature:
    """Drops captured values below DETAIL, keeping every field that is not a value.

    A declared type is part of the call's identity, not of its data, so suppression must not take
    it: a NARRATIVE-level artifact still has to say *which* method ran.
    """
    suppressed = [
        replace(p, rendered_value="", structured_value=None) for p in signature.parameters
    ]
    return replace(signature, parameters=suppressed)


# --------------------------------------------------------------------------- #
# No-op context                                                                #
# --------------------------------------------------------------------------- #
@contextmanager
def _noop_scope() -> Iterator[None]:
    yield


class _NoopSnapshot(ContextSnapshot):
    def activate(self) -> AbstractContextManager[None]:
        return _noop_scope()


class NoopNarrativeContext(NarrativeContext):
    """A context that discards all capture calls and always yields an empty tree."""

    _EMPTY = TraceTree([])
    _SNAPSHOT = _NoopSnapshot()

    def is_active(self) -> bool:
        return False

    def enter_method(self, signature: MethodSignature) -> SpanId | None:
        return None

    def exit_method_with_return(
        self,
        rendered_return_value: str | None,
        structured_return_value: RenderedValue | None = None,
        span_id: SpanId | None = None,
    ) -> None:
        return None

    def exit_method_with_exception(
        self,
        exception: BaseException,
        error_context: str | None = None,
        span_id: SpanId | None = None,
    ) -> None:
        return None

    def capture_trace(self) -> TraceTree:
        return self._EMPTY

    def reset(self) -> None:
        return None

    def snapshot(self) -> ContextSnapshot:
        return self._SNAPSHOT


NOOP_CONTEXT = NoopNarrativeContext()
