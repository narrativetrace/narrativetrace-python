# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Flat per-event canonical entries (``entry.schema.json``).

``CanonicalEntry`` / ``CanonicalEntryMapper`` / ``CanonicalEntrySerializer``. This is
the interoperability boundary for a *single* trace event, as opposed to :mod:`narrativetrace.export`
(the nested event stream) and :mod:`narrativetrace.chapter` (one service's whole contribution).

Field names on :class:`CanonicalEntry` are snake_case Python; the serialiser maps them to the
dotted schema names (``code_namespace`` → ``"code.namespace"``, ``nt_event_type`` →
``"nt.eventType"``).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from narrativetrace.concurrency import ThreadIdentity
from narrativetrace.events import (
    EnterEvent,
    ExitEvent,
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
    TraceEvent,
)
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext

SCHEMA_VERSION = "1.2"
"""The one canonical schema version this runtime stamps, everywhere.

Shared by the flat entry form, the chapter envelope and the OTel attribute mapper — Java bumps all
three in lockstep from ``CanonicalEntry.SCHEMA_VERSION`` (decision 2026-08-18), and three separate
literals is exactly how the stamp drifts away from the shape it describes.

1.1 added ``nt.narrationTemplate``. 1.2 added the additive nullable identity fields:
``nt.package``, ``nt.exceptionPackage``, ``nt.returnType``, the ``type`` property on
``nt.parameters`` items, thread identity (``thread.name``, ``thread.id``, ``nt.threadVirtual``),
and process resource identity (``host.name``, ``process.pid``, ``process.runtime.version``).
"""

_ENTRY_TYPE = "entry"

#: Service name stamped on entries when the host pins none.
#:
#: ``service`` is required by ``entry.schema.json``, so it must never be absent or blank.
#: This is OpenTelemetry's convention for "nobody said": ``unknown_service:`` plus the
#: runtime name. Cross-runtime contract (owner decision, 2026-08-28): every NarrativeTrace
#: runtime emits ``unknown_service:<runtime>`` with its own fixed suffix -- ``:java``,
#: ``:node``, ``:python``, ``:dotnet``, ``:swift``. The suffix is a literal, not a lookup
#: of the running executable, so the value stays deterministic across restarts and
#: deployments; conformance fixtures normalise the suffix away before comparing goldens.
UNKNOWN_SERVICE = "unknown_service:python"
_REDACTED = "[REDACTED]"
_NANOS_PER_MILLI = 1_000_000


@dataclass(frozen=True, slots=True)
class MonotonicAnchor:
    """Pins the monotonic clock that stamps events to wall-clock time.

    Events carry :func:`time.perf_counter_ns` readings — correct for durations, meaningless as an
    epoch. One anchor converts them to real timestamps; drift over a process lifetime is bounded.
    """

    epoch_millis: int
    monotonic_nanos: int

    def __post_init__(self) -> None:
        if self.epoch_millis < 0:
            raise ValueError("epoch_millis must not be negative")

    @classmethod
    def now(cls) -> MonotonicAnchor:
        """Reads both clocks once, pairing wall-clock time with the monotonic reading."""
        return cls(epoch_millis=int(time.time() * 1000), monotonic_nanos=time.perf_counter_ns())

    def timestamp(self, monotonic_nanos: int) -> str:
        """Formats an event's monotonic reading as UTC ISO-8601 with millisecond precision."""
        delta_millis = (monotonic_nanos - self.monotonic_nanos) // _NANOS_PER_MILLI
        moment = datetime.fromtimestamp((self.epoch_millis + delta_millis) / 1000, tz=UTC)
        return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ParameterEntry:
    """One method parameter in the ``nt.parameters`` array.

    ``type_name`` is the declared type (schema 1.2 ``type``), omitted from the wire form when the
    parameter carries no annotation.
    """

    name: str
    value: str
    redacted: bool = False
    type_name: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalEntry:
    """Flat canonical representation of a single trace event.

    Every field added by schema 1.1 and 1.2 is nullable and additive; an entry that carries none of
    them is still a valid 1.2 document, which is what lets a runtime adopt the identity fields it
    can supply without waiting for the ones it cannot.
    """

    timestamp: str
    level: str
    message: str
    nt_entry_type: str = _ENTRY_TYPE
    nt_event_type: str = ""
    nt_schema_version: str = SCHEMA_VERSION
    service: str = UNKNOWN_SERVICE
    environment: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    code_namespace: str | None = None
    code_function: str | None = None
    code_filepath: str | None = None
    code_lineno: int | None = None
    host_name: str | None = None
    process_pid: int | None = None
    process_runtime_version: str | None = None
    thread_name: str | None = None
    thread_id: int | None = None
    nt_thread_virtual: bool | None = None
    nt_trace_name: str | None = None
    nt_story_id: str | None = None
    nt_chapter_id: str | None = None
    nt_outcome: str | None = None
    nt_fork_id: str | None = None
    nt_branch_index: int | None = None
    nt_causal_id: str | None = None
    nt_package: str | None = None
    nt_exception_package: str | None = None
    nt_return_type: str | None = None
    nt_instance_id: str | None = None
    nt_narration_template: str | None = None
    duration_ms: int | None = None
    nt_parameters: list[ParameterEntry] | None = None
    nt_return_value: str | None = None
    exception_type: str | None = None
    exception_message: str | None = None


def _parameter_value(param: ParameterCapture) -> str:
    return _REDACTED if param.redacted else param.rendered_value


def _enter_message(sig: MethodSignature) -> str:
    rendered = ", ".join(f"{p.name}: {_parameter_value(p)}" for p in sig.parameters)
    return f"→ {sig.class_name}.{sig.method_name}({rendered})"


def _parameters(sig: MethodSignature) -> list[ParameterEntry] | None:
    if not sig.parameters:
        return None
    return [
        ParameterEntry(p.name, _parameter_value(p), p.redacted, p.type_name) for p in sig.parameters
    ]


def _package_of(exception: BaseException) -> str | None:
    """The module owning an exception class — ``nt.exceptionPackage``.

    ``exception.type`` stays a simple name so a message reads well; without the package, two
    same-named exceptions from different libraries are indistinguishable to a consumer.
    """
    return getattr(type(exception), "__module__", None)


def service_or_unknown(service_name: str | None) -> str:
    """Returns the pinned service name, or :data:`UNKNOWN_SERVICE` when the host pinned none.

    Public because ``service`` is required by both ``entry.schema.json`` and
    ``chapter.schema.json``: every writer needs the same fallback, and a second copy of the rule is
    how one of them ends up omitting the field.
    """
    if service_name is None or not service_name.strip():
        return UNKNOWN_SERVICE
    return service_name


def _with_correlation(entry: CanonicalEntry, span: SpanContext) -> CanonicalEntry:
    """Adds the span-derived fields every method entry and exit carries."""
    return replace(
        entry,
        service=service_or_unknown(span.service_name),
        environment=span.environment,
        host_name=span.host_name,
        process_pid=span.process_pid,
        process_runtime_version=span.runtime_version,
        trace_id=str(span.trace_id),
        span_id=str(span.span_id),
        parent_span_id=str(span.parent_span_id) if span.parent_span_id is not None else None,
        nt_trace_name=span.trace_id.human_name(),
        nt_story_id=span.story_id,
        nt_chapter_id=span.chapter_id,
    )


def with_thread_identity(entry: CanonicalEntry, thread: ThreadIdentity | None) -> CanonicalEntry:
    """Adds thread identity; an event captured without it keeps the schema's ``null``.

    Shared with :mod:`narrativetrace.tree_canonical`: the event mapper and the tree mapper must
    agree on what "not captured" looks like, and two copies of the rule is how they stop agreeing.
    """
    if thread is None:
        return entry
    return replace(
        entry,
        thread_name=thread.name,
        thread_id=thread.thread_id,
        nt_thread_virtual=thread.virtual,
    )


def _from_enter_event(event: EnterEvent, anchor: MonotonicAnchor) -> CanonicalEntry:
    sig = event.signature
    entry = CanonicalEntry(
        timestamp=anchor.timestamp(event.timestamp_nanos),
        level="trace",
        message=_enter_message(sig),
        nt_event_type="method_enter",
        code_namespace=sig.class_name,
        code_function=sig.method_name,
        nt_package=sig.package_name,
        nt_return_type=sig.return_type,
        nt_narration_template=sig.narration_template,
        nt_parameters=_parameters(sig),
    )
    return with_thread_identity(_with_correlation(entry, event.span_context), event.thread)


def _split_span_name(span_name: str | None) -> tuple[str, str]:
    """Splits ``Class.method`` at the *first* dot; a dotless name is a bare function."""
    name = span_name if span_name is not None else ""
    namespace, dot, function = name.partition(".")
    if not dot:
        return "", name
    return namespace, function


def _exit_message(span: SpanContext, outcome: TraceOutcome) -> str:
    if isinstance(outcome, Threw):
        return f"!! {type(outcome.exception).__name__}: {outcome.exception}"
    name = span.span_name if span.span_name is not None else "method"
    if isinstance(outcome, Returned) and outcome.rendered_value is not None:
        return f"← {name} returned {outcome.rendered_value}"
    if isinstance(outcome, Incomplete):
        return f"← {name} incomplete"
    return f"← {name} returned"


def _exit_outcome(outcome: TraceOutcome) -> str | None:
    if isinstance(outcome, Returned):
        return "success"
    if isinstance(outcome, Threw):
        return "failure"
    if isinstance(outcome, Incomplete):
        return "incomplete"
    return None


def _from_exit_event(event: ExitEvent, anchor: MonotonicAnchor) -> CanonicalEntry:
    span, outcome = event.span_context, event.outcome
    namespace, function = _split_span_name(span.span_name)
    threw = outcome if isinstance(outcome, Threw) else None
    returned = outcome if isinstance(outcome, Returned) else None
    entry = CanonicalEntry(
        timestamp=anchor.timestamp(event.timestamp_nanos),
        level="error" if threw is not None else "trace",
        message=_exit_message(span, outcome),
        nt_event_type="method_exit",
        code_namespace=namespace,
        code_function=function,
        nt_outcome=_exit_outcome(outcome),
        nt_return_value=returned.rendered_value if returned is not None else None,
        exception_type=type(threw.exception).__name__ if threw is not None else None,
        exception_message=str(threw.exception) if threw is not None else None,
        nt_exception_package=_package_of(threw.exception) if threw is not None else None,
    )
    return _with_correlation(entry, span)


_GROUP_EVENT_TYPES: dict[type[TraceEvent], str] = {
    ForkCreatedEvent: "fork",
    MergeEvent: "join",
    FireAndForgetEvent: "async_dispatch",
}


def _from_group_event(
    event: ForkCreatedEvent | MergeEvent | FireAndForgetEvent, anchor: MonotonicAnchor
) -> CanonicalEntry:
    """Group lifecycle markers have no span, so they carry only the group id."""
    event_type = _GROUP_EVENT_TYPES[type(event)]
    return CanonicalEntry(
        timestamp=anchor.timestamp(event.timestamp_nanos),
        level="trace",
        message=f"{event_type} [{event.group_id}]",
        nt_event_type=event_type,
        nt_fork_id=event.group_id,
    )


def entry_from_event(event: TraceEvent, *, anchor: MonotonicAnchor) -> CanonicalEntry:
    """Maps one :class:`TraceEvent` to its flat :class:`CanonicalEntry`."""
    if isinstance(event, EnterEvent):
        return _from_enter_event(event, anchor)
    if isinstance(event, ExitEvent):
        return _from_exit_event(event, anchor)
    if isinstance(event, ForkCreatedEvent | MergeEvent | FireAndForgetEvent):
        return _from_group_event(event, anchor)
    raise TypeError(f"unknown TraceEvent type: {type(event).__name__}")


# Attribute → schema key, in Java ``CanonicalEntrySerializer``'s emission order: universal
# fields, then OTel semantic conventions, then the ``nt.*`` extensions.
_FIELD_ORDER: tuple[tuple[str, str], ...] = (
    ("timestamp", "timestamp"),
    ("level", "level"),
    ("message", "message"),
    ("service", "service"),
    ("environment", "environment"),
    ("host.name", "host_name"),
    ("process.pid", "process_pid"),
    ("process.runtime.version", "process_runtime_version"),
    ("trace_id", "trace_id"),
    ("span_id", "span_id"),
    ("parent_span_id", "parent_span_id"),
    ("code.namespace", "code_namespace"),
    ("code.function", "code_function"),
    ("code.filepath", "code_filepath"),
    ("code.lineno", "code_lineno"),
    ("exception.type", "exception_type"),
    ("exception.message", "exception_message"),
    ("thread.name", "thread_name"),
    ("thread.id", "thread_id"),
    ("durationMs", "duration_ms"),
    ("nt.entryType", "nt_entry_type"),
    ("nt.eventType", "nt_event_type"),
    ("nt.schemaVersion", "nt_schema_version"),
    ("nt.traceName", "nt_trace_name"),
    ("nt.storyId", "nt_story_id"),
    ("nt.chapterId", "nt_chapter_id"),
    ("nt.outcome", "nt_outcome"),
    ("nt.forkId", "nt_fork_id"),
    ("nt.branchIndex", "nt_branch_index"),
    ("nt.causalId", "nt_causal_id"),
    ("nt.threadVirtual", "nt_thread_virtual"),
    ("nt.package", "nt_package"),
    ("nt.exceptionPackage", "nt_exception_package"),
    ("nt.returnType", "nt_return_type"),
    ("nt.instanceId", "nt_instance_id"),
    ("nt.narrationTemplate", "nt_narration_template"),
    ("nt.returnValue", "nt_return_value"),
    ("nt.parameters", "nt_parameters"),
)


def _parameter_document(parameter: ParameterEntry) -> dict[str, object]:
    """Renders one parameter; ``type`` is omitted rather than null when nothing was declared."""
    document: dict[str, object] = {
        "name": parameter.name,
        "value": parameter.value,
        "redacted": parameter.redacted,
    }
    if parameter.type_name is not None:
        document["type"] = parameter.type_name
    return document


def _wire_value(value: object) -> object:
    if isinstance(value, list):
        return [_parameter_document(parameter) for parameter in value]
    return value


def entry_document(entry: CanonicalEntry) -> dict[str, object]:
    """Renders an entry as a plain dict keyed by the dotted schema names, omitting unset fields."""
    if entry is None:
        raise ValueError("entry must not be None")
    doc: dict[str, object] = {}
    for key, attribute in _FIELD_ORDER:
        value = getattr(entry, attribute)
        if value is not None:
            doc[key] = _wire_value(value)
    return doc


def entry_to_json(entry: CanonicalEntry) -> str:
    """Serialises one entry to JSON using the canonical dotted field names."""
    return json.dumps(entry_document(entry), indent=2, ensure_ascii=False)
