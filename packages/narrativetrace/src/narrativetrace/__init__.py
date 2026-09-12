# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""narrativetrace — human- and LLM-readable narrative execution tracing.

This is the dependency-free core distribution. Integrations (pytest, OpenTelemetry,
structlog, ASGI, clarity, diagrams) ship as separate workspace packages.
"""

from narrativetrace.canonical import (
    CanonicalEntry,
    MonotonicAnchor,
    ParameterEntry,
    entry_document,
    entry_from_event,
    entry_to_json,
)
from narrativetrace.chapter import export_chapter as export_chapter_json
from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.config import ConfigResolver, DuplicateConfigurationError
from narrativetrace.context import (
    NOOP_CONTEXT,
    ContextSnapshot,
    ContextVarNarrativeContext,
    NarrativeContext,
    NoopNarrativeContext,
)
from narrativetrace.decorators import narrated, not_traced, on_error, traced
from narrativetrace.escape import control_sanitize, markdown_code, markdown_text
from narrativetrace.events import (
    EnterEvent,
    ExitEvent,
    FireAndForgetEvent,
    ForkCreatedEvent,
    MergeEvent,
    TraceEvent,
    span_id_of,
)
from narrativetrace.export import export as export_json
from narrativetrace.export import export_document as export_document_json
from narrativetrace.groups import FireAndForgetGroup, ForkJoinGroup
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel
from narrativetrace.logging_bridge import (
    LoggingTraceConsumer,
    NarrativeContextFilter,
    current_scope_keys,
    export_to_logger,
    request_log_scope,
)
from narrativetrace.loss import TraceLoss
from narrativetrace.markers import (
    NOT_TRACED_METADATA,
    narrative_summary,
    not_traced_field,
)
from narrativetrace.metadata import (
    ClientIp,
    EnduserId,
    HttpRoute,
    ServiceIdentity,
    SessionId,
    TenantId,
)
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.redaction import REDACTED_MARKER, RedactionPolicy
from narrativetrace.render import (
    FrontmatterBuilder,
    IndentedTextRenderer,
    MarkdownRenderer,
    NarrativeRenderer,
    ProseRenderer,
    ScenarioResult,
    StructuralTraceRenderer,
    TraceMetadata,
)
from narrativetrace.rendering import ValueRenderer
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext
from narrativetrace.trace_object import trace_object
from narrativetrace.tree import TraceTree, build_trace_tree
from narrativetrace.tree_canonical import export_canonical_entries
from narrativetrace.values import (
    BoolVal,
    FloatVal,
    InstantVal,
    IntVal,
    ListVal,
    NullVal,
    ObjectVal,
    RenderedValue,
    StringVal,
)

__version__ = "0.1.1"

__all__ = [
    "NOOP_CONTEXT",
    "NOT_TRACED_METADATA",
    "REDACTED_MARKER",
    "BoolVal",
    "CanonicalEntry",
    "ClientIp",
    "ConcurrencyInfo",
    "ConcurrencyKind",
    "ConfigResolver",
    "ContextSnapshot",
    "ContextVarNarrativeContext",
    "DuplicateConfigurationError",
    "EnduserId",
    "EnterEvent",
    "ExitEvent",
    "FireAndForgetEvent",
    "FireAndForgetGroup",
    "FloatVal",
    "ForkCreatedEvent",
    "ForkJoinGroup",
    "FrontmatterBuilder",
    "HttpRoute",
    "Incomplete",
    "IndentedTextRenderer",
    "InstantVal",
    "IntVal",
    "ListVal",
    "LoggingTraceConsumer",
    "MarkdownRenderer",
    "MergeEvent",
    "MethodSignature",
    "MonotonicAnchor",
    "NarrativeContext",
    "NarrativeContextFilter",
    "NarrativeRenderer",
    "NarrativeTraceConfig",
    "NoopNarrativeContext",
    "NullVal",
    "ObjectVal",
    "ParameterCapture",
    "ParameterEntry",
    "ProseRenderer",
    "RedactionPolicy",
    "RenderedValue",
    "Returned",
    "ScenarioResult",
    "ServiceIdentity",
    "SessionId",
    "SpanContext",
    "SpanId",
    "StringVal",
    "StructuralTraceRenderer",
    "TenantId",
    "Threw",
    "TraceEvent",
    "TraceId",
    "TraceLoss",
    "TraceMetadata",
    "TraceNode",
    "TraceOutcome",
    "TraceTree",
    "TracingLevel",
    "ValueRenderer",
    "__version__",
    "build_trace_tree",
    "control_sanitize",
    "current_scope_keys",
    "entry_document",
    "entry_from_event",
    "entry_to_json",
    "export_canonical_entries",
    "export_chapter_json",
    "export_document_json",
    "export_json",
    "export_to_logger",
    "markdown_code",
    "markdown_text",
    "narrated",
    "narrative_summary",
    "not_traced",
    "not_traced_field",
    "on_error",
    "request_log_scope",
    "span_id_of",
    "trace_object",
    "traced",
]
