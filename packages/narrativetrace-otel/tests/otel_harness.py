# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Test harness: a tracer wired to an in-memory exporter with span-lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, Tracer


@dataclass(frozen=True, slots=True)
class Harness:
    """A tracer wired to an in-memory exporter, with helpers to read finished spans."""

    tracer: Tracer
    exporter: InMemorySpanExporter

    def finished(self) -> list[ReadableSpan]:
        return list(self.exporter.get_finished_spans())

    def named(self, name: str) -> ReadableSpan:
        return next(s for s in self.finished() if s.name == name)

    def attrs(self, span: ReadableSpan | Span) -> dict[str, object]:
        """Returns a span's attributes as a plain dict (narrowing the Optional mapping)."""
        raw = getattr(span, "attributes", None)
        return dict(raw) if raw else {}

    def span_id(self, span: ReadableSpan) -> int:
        assert span.context is not None
        return int(span.context.span_id)

    def parent_id(self, span: ReadableSpan) -> int:
        assert span.parent is not None
        return int(span.parent.span_id)
