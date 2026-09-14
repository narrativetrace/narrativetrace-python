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
_UNNAMED_ALIAS = "P"
_PERCENT_RUN = re.compile(r"%%+")

_MERMAID_RESERVED_ALIASES = frozenset(
    {
        "sequencediagram",
        "participant",
        "actor",
        "create",
        "destroy",
        "box",
        "loop",
        "rect",
        "opt",
        "alt",
        "else",
        "par",
        "par_over",
        "and",
        "critical",
        "option",
        "break",
        "end",
        "links",
        "link",
        "properties",
        "details",
        "over",
        "note",
        "activate",
        "deactivate",
        "autonumber",
        "off",
        "title",
    }
)
"""Mermaid sequence-diagram keywords a bare alias token must never collide with, matched
case-insensitively -- the grammar declares ``%options case-insensitive``.

Sourced from every single-word literal lexer rule in ``sequenceDiagram.jison``
(mermaid-js/mermaid, ``develop`` branch, verified 2026-09-13): the keywords above, plus the
diagram-opening ``sequenceDiagram`` itself. ``title`` is included defensively -- its lexer rule
only fires when the keyword is followed by same-line text (``"title"\\s[^#\\n;]+``), so a bare
``title`` alias does not collide against today's grammar, but a future revision could drop that
requirement and a suffixed alias costs nothing. Words the grammar only recognizes as part of a
multi-word phrase (``"left of"``, ``"right of"``) are absent -- :func:`alias_token` can never
produce a token containing a space."""

_PLANTUML_RESERVED_WORDS = frozenset(
    {
        "participant",
        "actor",
        "boundary",
        "control",
        "entity",
        "database",
        "collections",
        "queue",
        "alt",
        "else",
        "opt",
        "loop",
        "par",
        "break",
        "critical",
        "group",
        "end",
        "note",
        "ref",
        "activate",
        "deactivate",
        "destroy",
        "create",
        "return",
        "box",
        "title",
        "header",
        "footer",
        "newpage",
        "autonumber",
        "hide",
        "show",
        "skinparam",
        "mainframe",
        "partition",
    }
)
"""PlantUML sequence-diagram keywords a bare (unquoted) participant/arrow token risks colliding
with, matched case-insensitively.

Sourced from plantuml.com/sequence-diagram (verified 2026-09-13): the participant-type keywords,
the block/control keywords, the messaging keywords, and the structural keywords above. PlantUML's
own docs demonstrate quoting as the escape for exactly this collision (``participant "I have a
really\\nlong name" as L``, ``"Bob()" -> "This is very\\nlong" as Long`` -- quoting works in a
message/arrow line, not only a declaration), which is why :func:`plain_mode_token` closes this
with the same quoting mechanism :func:`quote_if_needed` already uses for special characters,
rather than :func:`alias_token`'s suffix."""


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


def _needs_quoting_for_a_character(safe: str) -> bool:
    return any(c in _SPECIAL_CHARS for c in safe)


def _is_sequence_diagram_reserved_word(token: str) -> bool:
    """True when ``token``, compared case-insensitively as a WHOLE, is a bare keyword either
    grammar reserves -- never merely contains one as a substring (``endpoint`` is an ordinary
    name)."""
    lower = token.lower()
    return lower in _MERMAID_RESERVED_ALIASES or lower in _PLANTUML_RESERVED_WORDS


def quote_if_needed(name: str) -> str:
    """Sanitizes ``name`` via :func:`identifier`, then quotes it if it contains ``.``, ``-``,
    ``:``, ``<``, ``>`` or a space."""
    safe = identifier(name)
    return f'"{safe}"' if _needs_quoting_for_a_character(safe) else safe


def plain_mode_token(name: str) -> str:
    """As :func:`quote_if_needed`, but ALSO quotes when the whole (sanitized) name is a bare
    grammar keyword -- safe wherever the identifier is used AS the grammar token itself: a
    PLAIN-mode participant declaration or arrow endpoint, in either grammar.

    Deliberately a separate function from :func:`quote_if_needed`, not a universal change to it:
    Mermaid's alias mode reuses :func:`quote_if_needed` for the human-readable display name after
    ``as`` (``participant X as DisplayName``), which is never itself used as a bare token and is
    documented (see the Mermaid alias-mode tests) to keep a reserved word unescaped there --
    changing :func:`quote_if_needed` itself would have silently re-quoted that unrelated,
    already-shipped output.
    """
    safe = identifier(name)
    needs_quoting = _needs_quoting_for_a_character(safe) or _is_sequence_diagram_reserved_word(safe)
    return f'"{safe}"' if needs_quoting else safe


def alias_token(raw: str) -> str:
    """A bare Mermaid/PlantUML participant alias: a single unquotable token, safe unquoted both
    on a ``participant X as Name`` declaration and on every arrow line that names it.

    :func:`identifier` is not enough here -- an alias sits in grammar position, not text
    position, and its output can still carry a space, a colon, an arrow fragment (``->>``) or a
    quote, any one of which would split an arrow into the wrong number of tokens or splice a
    second participant into the line. This reduces the candidate to letters, digits and ``_``
    (mirrors Java's ``Character.isLetterOrDigit``, so a non-ASCII letter survives, matching the
    reference's own behavior) and falls back to :data:`_UNNAMED_ALIAS` when nothing survives --
    never an empty token, which would emit a malformed ``participant `` declaration or collapse
    an arrow's endpoint entirely. A class name with no uppercase letters and nothing hostile in
    it keeps its historical alias unchanged: ``scheduler`` stays ``scheduler``.

    Collision detection must run on this function's *output*, not the raw candidate: two
    distinct raw names that reduce to the same token (``a"b`` and ``a'b`` both fold to ``ab``)
    are the same participant unless the caller renumbers them apart.

    A token that collides with a Mermaid sequence-diagram keyword, case-insensitively, gets a
    trailing ``_``: a class literally named ``end`` used to yield that word, unchanged, as its
    own alias -- a bare token the grammar reserves for closing a block (``end``) or opening a
    declaration (``participant``), which the parser rejects outright rather than rendering. See
    :data:`_MERMAID_RESERVED_ALIASES`.
    """
    filtered = "".join(c for c in raw if c == "_" or c.isalnum())
    token = filtered[:_MAX_IDENTIFIER_LENGTH]
    if not token:
        return _UNNAMED_ALIAS
    return f"{token}_" if token.lower() in _MERMAID_RESERVED_ALIASES else token
