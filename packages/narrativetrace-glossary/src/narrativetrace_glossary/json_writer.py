# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Deterministic serializer for ``glossary.json``.

``GlossaryJsonWriter``. The committed glossary must be byte-identical whenever the
vocabulary is unchanged (anti-churn, ADR-012), so the layout is hand-rolled rather than delegated to
:func:`json.dumps`: contexts sorted by name, terms in the model's canonical ``(context, term)``
order, fixed key order, 2-space indent, string arrays and synonyms inline, trailing newline.
Volatile statistics are never emitted — those belong in build-directory reports.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from narrativetrace_glossary.models import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
)


def _quoted(value: str) -> str:
    """Renders a JSON string literal, escaping control characters but keeping non-ASCII readable."""
    return json.dumps(value, ensure_ascii=False)


def _render_string_array(values: Sequence[str]) -> str:
    return "[" + ", ".join(_quoted(value) for value in values) + "]"


def _render_context(context: BoundedContext) -> str:
    fields = [f'"packages": {_render_string_array(context.packages)}']
    if context.description is not None:
        fields.append(f'"description": {_quoted(context.description)}')
    return f"    {_quoted(context.name)}: {{\n      " + ",\n      ".join(fields) + "\n    }"


def _render_contexts(contexts: Mapping[str, BoundedContext]) -> str:
    if not contexts:
        return "{}"
    rendered = (_render_context(contexts[name]) for name in sorted(contexts))
    return "{\n" + ",\n".join(rendered) + "\n  }"


def _render_abbreviations(abbreviations: Mapping[str, str]) -> str:
    """Renders the accepted-shorthand section, sorted by abbreviation."""
    rendered = (
        f"    {_quoted(abbreviation)}: {_quoted(abbreviations[abbreviation])}"
        for abbreviation in sorted(abbreviations)
    )
    return '  "abbreviations": {\n' + ",\n".join(rendered) + "\n  },\n"


def _render_translations(translations: Mapping[str, str]) -> str:
    rendered = (
        f"        {_quoted(locale)}: {_quoted(translations[locale])}"
        for locale in sorted(translations)
    )
    return "{\n" + ",\n".join(rendered) + "\n      }"


def _render_synonym(synonym: SynonymAlias) -> str:
    body = f'{{ "alias": {_quoted(synonym.alias)}'
    if synonym.note is not None:
        body += f', "note": {_quoted(synonym.note)}'
    return f"        {body} }}"


def _render_synonyms(synonyms: Sequence[SynonymAlias]) -> str:
    return "[\n" + ",\n".join(_render_synonym(synonym) for synonym in synonyms) + "\n      ]"


def _render_term(term: GlossaryTerm) -> str:
    fields = [
        f'"term": {_quoted(term.term)}',
        f'"context": {_quoted(term.context)}',
        f'"kind": {_quoted(term.kind.value)}',
        f'"status": {_quoted(term.status.value)}',
    ]
    if term.definition is not None:
        fields.append(f'"definition": {_quoted(term.definition)}')
    if term.translations:
        fields.append(f'"translations": {_render_translations(term.translations)}')
    if term.synonyms:
        fields.append(f'"synonyms": {_render_synonyms(term.synonyms)}')
    if term.sources:
        fields.append(f'"sources": {_render_string_array(term.sources)}')
    fields.append(f'"firstSeen": {_quoted(term.first_seen.isoformat())}')
    return "    {\n      " + ",\n      ".join(fields) + "\n    }"


def _render_terms(terms: Sequence[GlossaryTerm]) -> str:
    if not terms:
        return "[]"
    return "[\n" + ",\n".join(_render_term(term) for term in terms) + "\n  ]"


def write_glossary_json(glossary: Glossary) -> str:
    """Serialises a glossary to its canonical JSON text.

    The result is a pure function of the glossary's vocabulary — the same vocabulary always renders
    byte-identically, so committing the output produces no diff churn.

    The ``abbreviations`` section is omitted entirely when empty, and the model stamps such a
    glossary at schema 1: a repository that never declared shorthand writes exactly the bytes it
    wrote before the section existed.
    """
    if not isinstance(glossary, Glossary):
        raise TypeError("glossary must be a Glossary")
    abbreviations = _render_abbreviations(glossary.abbreviations) if glossary.abbreviations else ""
    document = (
        "{\n"
        f'  "schemaVersion": {glossary.schema_version},\n'
        f'  "contexts": {_render_contexts(glossary.contexts)},\n'
        f"{abbreviations}"
        f'  "terms": {_render_terms(glossary.terms)}\n'
        "}\n"
    )
    assert document.endswith("}\n"), "canonical file must end with a trailing newline"
    return document
