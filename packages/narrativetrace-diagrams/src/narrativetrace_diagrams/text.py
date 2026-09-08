# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Sanitizers for text interpolated into sequence-diagram grammars.

``DiagramText`` + the ``quoteIfNeeded`` helper. Diagram grammars are line-oriented: a
raw newline in a message terminates the statement and the next physical line is parsed as a
directive (Mermaid ``click`` interactions, PlantUML ``!include`` — SSRF / local-file read). Folding
every ISO control character to a space keeps the whole value on one physical line. A lone surrogate
code point is folded too, for the same reason ``control_sanitize`` treats it as hostile (a security
fuzz suite finding): no UTF-8 sink can encode it.

Adversarial-audit mirror (2026-09-02): :func:`identifier` is the one sanitizer for *metadata*
(class/method/parameter/exception-type names) shared by both grammars, applying the union of
their hazards — neither Mermaid nor PlantUML can escape a ``"`` inside a quoted name, so the
character must stop being a quote; Mermaid reads ``%%`` as a comment opener wherever it appears.
Unlike a rendered *value*, metadata never passes through ``control_sanitize`` upstream, so this
module folds controls and surrogates itself rather than assuming a caller already did.
"""

from __future__ import annotations

import re

_SPECIAL_CHARS = frozenset(".-: <>")
_MAX_IDENTIFIER_LENGTH = 200
_UNNAMED = "<unnamed>"
_PERCENT_RUN = re.compile(r"%%+")


def _is_iso_control(codepoint: int) -> bool:
    return codepoint <= 0x1F or 0x7F <= codepoint <= 0x9F


def _is_surrogate(codepoint: int) -> bool:
    return 0xD800 <= codepoint <= 0xDFFF


def _is_hostile(codepoint: int) -> bool:
    return _is_iso_control(codepoint) or _is_surrogate(codepoint)


def diagram_message(text: str) -> str:
    """Folds every ISO control character and lone surrogate to a single space so a value cannot
    inject a new line or an unencodable code point."""
    return "".join(" " if _is_hostile(ord(c)) else c for c in text)


def identifier(name: str) -> str:
    """Sanitizes a class/method/parameter/exception-type name for interpolation into either
    diagram grammar: folds controls and surrogates to spaces (no injected statement, no
    unencodable output), turns ``"`` into ``'`` (no escaping a quote from inside a quoted name),
    breaks up any ``%%`` run (Mermaid comment opener), caps length, and maps an empty/all-hostile/
    all-blank name to :data:`_UNNAMED` rather than emitting a bare, malformed declaration.
    """
    folded = "".join(" " if _is_hostile(ord(c)) else c for c in name).replace('"', "'")
    folded = _PERCENT_RUN.sub(lambda m: " ".join(m.group(0)), folded)
    if not folded.strip():
        return _UNNAMED
    if len(folded) > _MAX_IDENTIFIER_LENGTH:
        return f"{folded[:_MAX_IDENTIFIER_LENGTH]}…"
    return folded


def quote_if_needed(name: str) -> str:
    """Sanitizes ``name`` via :func:`identifier`, then quotes it if it contains ``.``, ``-``,
    ``:``, ``<``, ``>`` or a space."""
    safe = identifier(name)
    if any(c in _SPECIAL_CHARS for c in safe):
        return f'"{safe}"'
    return safe
