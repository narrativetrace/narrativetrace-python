# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Schema-strict reader for ``glossary.json``.

``GlossaryJsonReader``. The committed glossary is hand-curated, so a typo — an unknown
key, a wrong JSON type, a bad enum label, a malformed date — must fail loudly at load rather than be
silently dropped. Parsing itself delegates to :mod:`json` (Java hand-rolls a parser); everything
after it is validation, and every structural rule is enforced by the model constructors this reader
calls.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from datetime import date
from typing import Any

from narrativetrace_glossary.models import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
    TermKind,
    TermStatus,
)

_ROOT_KEYS = frozenset({"schemaVersion", "contexts", "abbreviations", "terms"})
_CONTEXT_KEYS = frozenset({"packages", "description"})
_TERM_KEYS = frozenset(
    {
        "term",
        "context",
        "kind",
        "status",
        "definition",
        "translations",
        "synonyms",
        "sources",
        "firstSeen",
    }
)
_SYNONYM_KEYS = frozenset({"alias", "note"})

# Java parses with ISO_LOCAL_DATE. ``date.fromisoformat`` is laxer — it also accepts the basic
# form ``20260811`` and ISO week dates — so the extended form is required explicitly.
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _as_object(value: object, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a JSON object")
    return value


def _as_array(value: object, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{what} must be a JSON array")
    return value


def _as_string(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{what} must be a JSON string")
    return value


def _as_int(value: object, what: str) -> int:
    """Accepts only a JSON integer — ``bool`` is an ``int`` in Python and must not slip through."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{what} must be a JSON integer")
    return value


def _required(body: dict[str, Any], key: str) -> Any:
    """Reads a key that must be present; an explicit ``null`` counts as missing, as in Java."""
    value = body.get(key)
    if value is None:
        raise ValueError(f"missing required key '{key}'")
    return value


def _optional_string(body: dict[str, Any], key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    return _as_string(value, key)


def _reject_unknown_keys(body: dict[str, Any], known: Collection[str], what: str) -> None:
    for key in body:
        if key not in known:
            raise ValueError(f"unknown key '{key}' in {what}")


def _read_string_list(value: object, what: str) -> list[str]:
    return [_as_string(element, f"{what} element") for element in _as_array(value, what)]


def _read_kind(label: str) -> TermKind:
    try:
        return TermKind(label)
    except ValueError as error:
        raise ValueError(f"unknown term kind '{label}'") from error


def _read_status(label: str) -> TermStatus:
    try:
        return TermStatus(label)
    except ValueError as error:
        raise ValueError(f"unknown term status '{label}'") from error


def _read_date(text: str) -> date:
    if not _ISO_DATE.match(text):
        raise ValueError(f"invalid firstSeen date '{text}'")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"invalid firstSeen date '{text}'") from error


def _read_translations(body: dict[str, Any]) -> dict[str, str]:
    if "translations" not in body:
        return {}
    raw = _as_object(body["translations"], "translations")
    return {locale: _as_string(text, f"translation '{locale}'") for locale, text in raw.items()}


def _read_abbreviations(body: dict[str, Any]) -> dict[str, str]:
    """Reads the accepted-shorthand section, absent below schema 2 and optional at every version.

    The section is additive and harmless, so it is accepted on a file stamped ``1`` rather than
    refused — refusing would buy nothing and create a migration cliff between runtimes whose readers
    ship at different times. The model raises such a glossary's stamp to 2 on construction.
    """
    if "abbreviations" not in body:
        return {}
    raw = _as_object(body["abbreviations"], "abbreviations")
    return {
        abbreviation: _as_string(expansion, f"expansion of abbreviation '{abbreviation}'")
        for abbreviation, expansion in raw.items()
    }


def _read_synonym(element: object) -> SynonymAlias:
    synonym = _as_object(element, "synonym entry")
    _reject_unknown_keys(synonym, _SYNONYM_KEYS, "synonym")
    return SynonymAlias(
        _as_string(_required(synonym, "alias"), "alias"), _optional_string(synonym, "note")
    )


def _read_synonyms(body: dict[str, Any]) -> list[SynonymAlias]:
    if "synonyms" not in body:
        return []
    return [_read_synonym(element) for element in _as_array(body["synonyms"], "synonyms")]


def _read_sources(body: dict[str, Any]) -> list[str]:
    if "sources" not in body:
        return []
    return _read_string_list(body["sources"], "sources")


def _read_term(element: object) -> GlossaryTerm:
    body = _as_object(element, "term entry")
    _reject_unknown_keys(body, _TERM_KEYS, "term")
    return GlossaryTerm(
        _as_string(_required(body, "term"), "term"),
        _as_string(_required(body, "context"), "context"),
        _read_kind(_as_string(_required(body, "kind"), "kind")),
        _read_status(_as_string(_required(body, "status"), "status")),
        _optional_string(body, "definition"),
        _read_translations(body),
        _read_synonyms(body),
        _read_sources(body),
        first_seen=_read_date(_as_string(_required(body, "firstSeen"), "firstSeen")),
    )


def _read_context(name: str, element: object) -> BoundedContext:
    body = _as_object(element, f"context '{name}'")
    _reject_unknown_keys(body, _CONTEXT_KEYS, f"context '{name}'")
    return BoundedContext(
        name,
        _read_string_list(_required(body, "packages"), "packages"),
        _optional_string(body, "description"),
    )


def _read_contexts(raw: dict[str, Any]) -> dict[str, BoundedContext]:
    return {name: _read_context(name, element) for name, element in raw.items()}


def _parse(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"malformed glossary JSON: {error}") from error


def read_glossary_json(text: str) -> Glossary:
    """Parses glossary JSON into a validated :class:`Glossary`.

    Raises :class:`ValueError` on malformed JSON, unknown or missing keys, wrong JSON types, bad
    enum labels, malformed dates, and on any structural violation the model rejects.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    root = _as_object(_parse(text), "document root")
    _reject_unknown_keys(root, _ROOT_KEYS, "glossary")
    return Glossary(
        contexts=_read_contexts(_as_object(_required(root, "contexts"), "contexts")),
        terms=[_read_term(element) for element in _as_array(_required(root, "terms"), "terms")],
        abbreviations=_read_abbreviations(root),
        schema_version=_as_int(_required(root, "schemaVersion"), "schemaVersion"),
    )
