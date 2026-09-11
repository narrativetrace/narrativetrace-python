# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Reads the shared hostile corpus (``resources/hostile-corpus/*.json``).

``HostileCorpus``. Each JSON file holds one or more arrays of case objects; a case is
either a literal value/template or a ``repeat`` specification (``prefix + unit * count + suffix``)
that expands a large input without a large fixture file. Loading is cached per file, since every
property test in this package reads the same shared files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from hostile_redaction_kinds import build as _build_kind_payload

_CORPUS_DIR = Path(__file__).parent / "resources" / "hostile-corpus"


def _materialize(case: dict[str, Any], literal_field: str) -> str:
    """Resolves a case's textual payload: a literal field, or a ``repeat`` expansion."""
    if literal_field in case:
        value = case[literal_field]
        return "" if value is None else str(value)
    repeat = case["repeat"]
    body = str(repeat["unit"]) * int(repeat["count"])
    prefix = str(case.get("prefix", ""))
    suffix = str(case.get("suffix", ""))
    return prefix + body + suffix


@dataclass(frozen=True, slots=True)
class CorpusCase:
    """A hostile scalar value (``strings.json``, ``injection.json``)."""

    id: str
    description: str
    value: str

    def __str__(self) -> str:
        return self.id


@dataclass(frozen=True, slots=True)
class HeaderCase:
    """A W3C trace-context header value (``headers.json``)."""

    id: str
    description: str
    value: str
    accepted: bool

    def __str__(self) -> str:
        return self.id


@dataclass(frozen=True, slots=True)
class TemplateCase:
    """An ``@narrated``/``@on_error`` template string (``templates.json``)."""

    id: str
    description: str
    template: str
    values: str
    expect: str | None

    @property
    def expects_redaction(self) -> bool:
        return self.expect == "redacted"

    def __str__(self) -> str:
        return self.id


@dataclass(frozen=True, slots=True)
class GraphCase:
    """A declarative object-graph shape (``graphs.json``): either a ``layers`` stack (index 0
    innermost) or a ``kind``-named shape a stack cannot express."""

    id: str
    description: str
    kind: str | None
    layers: tuple[str, ...] | None
    layer: str | None
    container: str | None
    member: str | None
    state: str | None
    payload: str | None
    n: int | None

    @property
    def carries_secret(self) -> bool:
        return self.payload == "secret-record"

    def __str__(self) -> str:
        return self.id


@dataclass(frozen=True, slots=True)
class RedactionCase:
    """One row of ``redaction.json``: a sensitive field name, a sensitive value shape, or (added
    2026-09-11, the family-wide ``__str__``-trust fix) a named ``kind`` -- a live composite
    ``hostile_redaction_kinds`` builds, the redaction-corpus counterpart to ``graphs.json``'s
    ``kind`` mechanism for object-graph shapes.

    A row names exactly one of a field (``name`` plus the ``canary`` planted behind it), a value
    (``value``, which is its own canary because the shape *is* the secret), or a ``kind`` (plus
    the ``canary`` the named builder plants somewhere in the composite it returns) -- never more
    than one, never none; ``expect`` says which way the assertion runs.
    """

    id: str
    description: str
    name: str | None
    value: str | None
    canary: str | None
    expect: str
    kind: str | None = None

    @property
    def expects_redaction(self) -> bool:
        return self.expect == "redacted"

    @property
    def is_name(self) -> bool:
        """Whether this row names a field rather than carrying a bare value or a ``kind``."""
        return self.name is not None

    @property
    def is_kind(self) -> bool:
        """Whether this row names a live composite ``hostile_redaction_kinds`` builds."""
        return self.kind is not None

    @property
    def secret(self) -> str:
        """The string the oracle looks for: the canary for a name or ``kind`` case, the value
        itself for a value case."""
        if self.is_name or self.is_kind:
            return self.canary or ""
        return self.value or ""

    @property
    def payload(self) -> object:
        """The object to render: the value alone, a one-entry mapping under the sensitive field
        name, or (for a ``kind`` row) the live composite ``hostile_redaction_kinds.build``
        returns."""
        if self.is_kind:
            assert self.kind is not None  # narrows for mypy; is_kind already guarantees this
            return _build_kind_payload(self.kind, self.canary or "")
        return {self.name: self.canary} if self.is_name else self.value

    def __str__(self) -> str:
        return self.id


@dataclass(frozen=True, slots=True)
class TraceShapeCase:
    """A declarative ``TraceNode`` call-tree shape (``trace-shapes.json``): a linear ``chain``
    ``n`` deep, or a ``cycle`` ring of ``n`` nodes (``n == 1`` holds itself)."""

    id: str
    description: str
    kind: str
    n: int

    def __str__(self) -> str:
        return self.id


def _corpus_case(node: dict[str, Any]) -> CorpusCase:
    return CorpusCase(node["id"], node["description"], _materialize(node, "value"))


def _header_case(node: dict[str, Any]) -> HeaderCase:
    return HeaderCase(
        node["id"],
        node["description"],
        _materialize(node, "value"),
        accepted=node.get("accepted", False),
    )


def _template_case(node: dict[str, Any]) -> TemplateCase:
    return TemplateCase(
        node["id"],
        node["description"],
        _materialize(node, "template"),
        node["values"],
        node.get("expect"),
    )


def _redaction_case(node: dict[str, Any]) -> RedactionCase:
    return RedactionCase(
        node["id"],
        node["description"],
        node.get("name"),
        node.get("value"),
        node.get("canary"),
        node["expect"],
        node.get("kind"),
    )


def _graph_case(node: dict[str, Any]) -> GraphCase:
    layers = node.get("layers")
    return GraphCase(
        node["id"],
        node["description"],
        node.get("kind"),
        tuple(layers) if layers is not None else None,
        node.get("layer"),
        node.get("container"),
        node.get("member"),
        node.get("state"),
        node.get("payload"),
        node.get("n"),
    )


@lru_cache
def _load(name: str) -> dict[str, Any]:
    path = _CORPUS_DIR / name
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


@lru_cache
def strings() -> tuple[CorpusCase, ...]:
    """Hostile scalar values feeding the value renderer and every output format."""
    return tuple(_corpus_case(c) for c in _load("strings.json")["cases"])


@lru_cache
def injections() -> tuple[CorpusCase, ...]:
    """Prompt-injection payloads feeding the AI-consumer containment oracle."""
    return tuple(_corpus_case(c) for c in _load("injection.json")["cases"])


@lru_cache
def names() -> tuple[CorpusCase, ...]:
    """Test class and method names feeding the artifact writers that turn one into a path."""
    return tuple(_corpus_case(c) for c in _load("names.json")["cases"])


@lru_cache
def redactions() -> tuple[RedactionCase, ...]:
    """Sensitive field names and national-id value shapes feeding the name deny-list and the
    value-shape matcher."""
    return tuple(_redaction_case(c) for c in _load("redaction.json")["cases"])


@lru_cache
def traceparents() -> tuple[HeaderCase, ...]:
    """W3C ``traceparent`` header values."""
    return tuple(_header_case(c) for c in _load("headers.json")["traceparent"])


@lru_cache
def tracestates() -> tuple[HeaderCase, ...]:
    """W3C ``tracestate`` header values (carried as data, never parsed by this runtime)."""
    return tuple(_header_case(c) for c in _load("headers.json")["tracestate"])


@lru_cache
def templates() -> tuple[TemplateCase, ...]:
    """``@narrated``/``@on_error`` template strings."""
    return tuple(_template_case(c) for c in _load("templates.json")["cases"])


@lru_cache
def graphs() -> tuple[GraphCase, ...]:
    """Declarative object-graph shapes feeding the value renderer."""
    return tuple(_graph_case(c) for c in _load("graphs.json")["cases"])


def _trace_shape_case(node: dict[str, Any]) -> TraceShapeCase:
    return TraceShapeCase(node["id"], node["description"], node["kind"], node["n"])


@lru_cache
def trace_shapes() -> tuple[TraceShapeCase, ...]:
    """Declarative ``TraceNode`` call-tree shapes feeding the tree-walk bound."""
    return tuple(_trace_shape_case(c) for c in _load("trace-shapes.json")["cases"])
