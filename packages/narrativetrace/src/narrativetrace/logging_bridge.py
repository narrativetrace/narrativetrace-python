# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Bridge that mirrors trace events to the stdlib :mod:`logging` framework.

``Slf4jTraceEventListener``. :class:`LoggingTraceConsumer` is an event consumer
(attach it as a :class:`~narrativetrace.pipeline.dual_path.DualPathPipeline` sync listener) that
logs enter/return at DEBUG (Java TRACE has no stdlib analog — plan decision point 3), exceptions
at WARNING as ``!! {type}: {message} [{error_context}]`` (control-sanitised), and fork/join/
fire-and-forget lifecycle lines.

:class:`NarrativeContextFilter` is the MDC analog: a logging ``Filter`` that stamps the canonical
keys of the current (innermost) traced span onto *every* record. Keys adopt Java's vocabulary:
``nt.class``/``nt.method``/``nt.depth`` and ``traceId``/``traceName``/``spanId``/``parentSpanId``/
``service.name``/``service.version``/``service.environment``. :func:`set_run_name` (the pytest
plugin's session hook calls it, mirroring Java's ``RunListener`` SPI attaching to MDC) adds
``runName`` -- the enclosing test-suite run's own three-word phrase, not a per-trace key at all
(2026-09-13 ruling, item 2) -- to every one of them for the run's whole duration, so one grep finds
one run's log lines the way ``traceId``/``traceName`` already let one grep find one trace's.
``traceName``/``runName`` are always present once :class:`NarrativeContextFilter` has touched a
record, defaulting to ``""`` when no trace/run is active -- see :data:`_ALWAYS_PRESENT_KEYS`.

**One consumer per event stream, many handlers.** Two :class:`LoggingTraceConsumer` instances
processing the *same* event stream (e.g. both attached as listeners on one pipeline) used to
corrupt ``nt.depth``: it was tracked on one stack shared by every instance on the same
thread/task, so each instance's push/pop interleaved with the other's and both misreported depth
for the same event. ``nt.depth`` is now a private counter on each instance (still a
:class:`contextvars.ContextVar`, so it stays isolated per thread/task the way it always was) —
two instances replaying the same stream now each report the correct depth independently, with
nothing to corrupt. :class:`NarrativeContextFilter` and the ``structlog`` processor are
unaffected: they read the shared MDC key *dict* for the innermost frame (class/method/trace
identity, the same for every instance processing one event), never a consumer's own depth
counter. Prefer one consumer per stream regardless — add extra ``logging.Handler``\\ s to its
logger for more destinations instead of a second consumer. See
``guides/logging.md#one-consumer-per-stream``.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.escape import control_sanitize
from narrativetrace.events import (
    EnterEvent,
    ExitEvent,
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
    TraceEvent,
)
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.pipeline.event_store import EventStore
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree

_DEFAULT_LOGGER_NAME = "narrativetrace"

_SCOPE_STACK: contextvars.ContextVar[list[dict[str, str]] | None] = contextvars.ContextVar(
    "narrativetrace_log_scope", default=None
)

# Request-level correlation keys (from an HTTP boundary), stamped beneath any active method scope.
_REQUEST_SCOPE: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "narrativetrace_request_scope", default=None
)

# The enclosing test-suite run's own phrase (2026-09-13 ruling, item 2) -- a plain module global,
# not a ContextVar like the scopes above: a run name is the SAME value for the whole process's
# test-suite execution, on every thread and task, not a value that should vary by call stack. The
# pytest plugin's session hook sets it once (the same SPI-attach-to-MDC shape this family uses
# elsewhere) and clears it when the session ends.
_run_name: str | None = None


def set_run_name(run_name: str | None) -> None:
    """Sets ``runName`` for every log line this process emits from now on -- the seam a test-suite
    integration (the pytest plugin's session hook) uses to attach the run's identity without this
    module knowing anything about pytest. ``None`` clears it (session end)."""
    global _run_name  # noqa: PLW0603 - the whole-process run name is deliberately not scoped
    _run_name = run_name


def current_run_name() -> str | None:
    """The active run's three-word phrase, or ``None`` outside a tracked test-suite execution."""
    return _run_name


def _stack() -> list[dict[str, str]]:
    stack = _SCOPE_STACK.get()
    if stack is None:
        stack = []
        _SCOPE_STACK.set(stack)
    return stack


@contextmanager
def request_log_scope(keys: dict[str, str]) -> Iterator[None]:
    """Stamps request-level correlation ``keys`` onto every record for the ``with`` body.

    The request-filter MDC population: keys sit *beneath* any active per-method scope, so
    an intervening span's keys win on overlap while request-only keys (HTTP method/route) persist.
    """
    token = _REQUEST_SCOPE.set(dict(keys))
    try:
        yield
    finally:
        _REQUEST_SCOPE.reset(token)


class EventType(Enum):
    """Buckets for per-event log-level overrides."""

    ENTRY = "entry"
    RETURN = "return"
    EXCEPTION = "exception"


def current_scope_keys() -> dict[str, str]:
    """The canonical correlation keys for the current scope (request keys + innermost span).

    Shared by :class:`NarrativeContextFilter` (stdlib) and the ``narrativetrace-structlog``
    processor so both emit an identical key set — the single source of MDC vocabulary.
    """
    merged: dict[str, str] = {}
    if _run_name is not None:
        merged["runName"] = _run_name
    request_scope = _REQUEST_SCOPE.get()
    if request_scope:
        merged.update(request_scope)
    stack = _SCOPE_STACK.get()
    if stack:
        merged.update(stack[-1])
    return merged


_ALWAYS_PRESENT_KEYS = ("traceName", "runName")
"""Defaulted to ``""`` on every record even outside an active scope/run (the Logback pattern-layout
``%X{}`` convention this port mirrors: printing blank for an absent MDC key rather than raising), so
a log format string referencing ``%(traceName)s``/``%(runName)s`` never raises ``KeyError`` on a
record :class:`NarrativeContextFilter` has already touched."""


class NarrativeContextFilter(logging.Filter):
    """Stamps the current innermost span's canonical keys onto every log record (MDC analog)."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in current_scope_keys().items():
            record.__dict__.setdefault(key, value)
        for key in _ALWAYS_PRESENT_KEYS:
            record.__dict__.setdefault(key, "")
        return True


def _span_keys(span_context: SpanContext) -> dict[str, str]:
    keys: dict[str, str] = {
        "traceId": str(span_context.trace_id),
        "traceName": span_context.trace_id.human_name(),
        "spanId": str(span_context.span_id),
    }
    if _run_name is not None:
        keys["runName"] = _run_name
    if span_context.parent_span_id is not None:
        keys["parentSpanId"] = str(span_context.parent_span_id)
    if span_context.service_name is not None:
        keys["service.name"] = span_context.service_name
    if span_context.service_version is not None:
        keys["service.version"] = span_context.service_version
    if span_context.environment is not None:
        keys["service.environment"] = span_context.environment
    return keys


class LoggingTraceConsumer:
    """An event consumer that logs trace events via the stdlib logging framework."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        levels: dict[EventType, int] | None = None,
    ) -> None:
        self._logger = logger if logger is not None else logging.getLogger(_DEFAULT_LOGGER_NAME)
        overrides = levels or {}
        self._entry = overrides.get(EventType.ENTRY, logging.DEBUG)
        self._return = overrides.get(EventType.RETURN, logging.DEBUG)
        self._exception = overrides.get(EventType.EXCEPTION, logging.WARNING)
        # This instance's own depth counter -- never shared with another LoggingTraceConsumer, so
        # a second instance replaying the same stream cannot corrupt it (see module docstring). A
        # fresh ContextVar per instance still isolates concurrent threads/tasks the way the old
        # shared stack did.
        self._depth: contextvars.ContextVar[int] = contextvars.ContextVar(
            f"narrativetrace_consumer_depth_{id(self)}", default=0
        )

    def __call__(self, event: TraceEvent) -> None:
        self.accept(event)

    def accept(self, event: TraceEvent) -> None:
        """Logs a single trace event."""
        if isinstance(event, EnterEvent):
            self._log_enter(event)
        elif isinstance(event, ExitEvent):
            self._log_exit(event)
        elif isinstance(event, ForkCreatedEvent):
            self._logger.log(self._entry, "⑂ fork group created [groupId: %s]", event.group_id)
        elif isinstance(event, MergeEvent):
            self._logger.log(
                self._entry,
                "⑃ fork joined [groupId: %s, members: %s]",
                event.group_id,
                event.member_count,
            )
        elif isinstance(event, FireAndForgetEvent):
            self._logger.log(
                self._entry, "⤳ fire-and-forget launched [groupId: %s]", event.group_id
            )

    def _log_enter(self, enter: EnterEvent) -> None:
        sig = enter.signature
        params = ", ".join(
            f"{p.name}: {'[REDACTED]' if p.redacted else p.rendered_value}" for p in sig.parameters
        )
        keys = _span_keys(enter.span_context)
        keys["nt.class"] = sig.class_name
        keys["nt.method"] = sig.method_name
        depth = self._depth.get() + 1
        self._depth.set(depth)
        keys["nt.depth"] = str(depth)
        _stack().append(keys)
        self._logger.log(
            self._entry, "→ %s.%s(%s)", sig.class_name, sig.method_name, params, extra=keys
        )

    def _log_exit(self, exit_event: ExitEvent) -> None:
        stack = _stack()
        if stack:
            stack.pop()
        depth = max(self._depth.get() - 1, 0)
        self._depth.set(depth)
        keys = _span_keys(exit_event.span_context)
        keys["nt.depth"] = str(depth)
        outcome = exit_event.outcome
        if isinstance(outcome, Returned):
            self._logger.log(self._return, "← returned: %s", outcome.rendered_value, extra=keys)
        elif isinstance(outcome, Threw):
            self._log_exception(outcome.exception, exit_event.error_context, keys)

    def _log_exception(
        self, exception: BaseException, error_context: str | None, keys: dict[str, str]
    ) -> None:
        exc_type = type(exception).__name__
        message = control_sanitize(str(exception))
        if error_context is not None:
            self._logger.log(
                self._exception,
                "!! %s: %s [%s]",
                exc_type,
                message,
                control_sanitize(error_context),
                extra=keys,
            )
        else:
            self._logger.log(self._exception, "!! %s: %s", exc_type, message, extra=keys)


def export_to_logger(
    trace: TraceTree,
    logger: logging.Logger | None = None,
    levels: dict[EventType, int] | None = None,
) -> None:
    """Sends an already-captured ``trace`` to ``logger`` in one call.

    The one-call equivalent of giving a context its own :class:`~narrativetrace.pipeline.
    event_store.EventStore`, running the code, and replaying ``store.events()`` through a
    :class:`LoggingTraceConsumer` by hand — this does that replay internally, on a private
    context/store the caller never sees, so ``ContextVarNarrativeContext()`` can stay parameter-
    free at the call site::

        trace = context.capture_trace()
        export_to_logger(trace)

    Each call replays into a fresh :class:`LoggingTraceConsumer`, so it obeys the "one consumer
    per stream" rule on its own (see the module docstring) — safe to call more than once, even
    concurrently, from different threads/tasks.

    The replay carries ``trace``'s own :attr:`~narrativetrace.tree.TraceTree.trace_id` (so
    ``traceName`` in the logged records names the *captured* trace, not a fresh one minted by
    this replay) when the tree has one -- an empty tree (``trace_id is None``) has no identity to
    carry, so the replay context is left to generate its own rather than pass ``None`` through
    :meth:`~narrativetrace.context.NarrativeContext.adopt_trace_id`. ``runName`` needs no such
    plumbing: :class:`LoggingTraceConsumer` reads the process-wide :func:`current_run_name`
    directly, so the run active when ``export_to_logger`` is called is the run these records
    carry, regardless of which context replays them.
    """
    store = EventStore()
    replay_context = ContextVarNarrativeContext(store=store)
    if trace.trace_id is not None:
        replay_context.adopt_trace_id(trace.trace_id)
    for root in trace.roots:
        replay_context.emit_trace_node(root, None)
    consumer = LoggingTraceConsumer(logger, levels)
    for event in store.events():
        consumer.accept(event)
