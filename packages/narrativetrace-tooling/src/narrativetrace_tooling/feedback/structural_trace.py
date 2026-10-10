# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Whether a file is a structural trace — the one artifact a report may attach, because it is the
one artifact that carries no runtime value by construction.

Ports Java ``StructuralTrace``, against this runtime's own ``.nt`` grammar
(``documentation/structural-trace-format.md``). INTENT: defence in depth over the value-free rules,
not a substitute for them. The rules decide about TEXT; this decides about a FILE's claim to be a
``.nt``. A rendered narrative copied to a ``.nt`` name is caught by the rules anyway — it is full of
values — but a file that passes the rules while not being a structural trace at all (a log with
nothing interesting in it, a half-written note) is not the attachment the report promises, and
attaching it would put an unreviewed file shape into a public issue.

**@llmNote** The grammar is the published one: a ``scenario:`` header, then call lines
``Type.method_name(name, name)`` at two-space indent per depth, each with an optional outcome of the
returned marker, ``!! TypeName`` or the incomplete marker — plus this runtime's concurrency markers
``~ fork [2]``, ``~ async [2]`` and ``~ fire-and-forget`` — either may open with a span id such as
``#1.3`` (a position, never a value). Anything else makes the whole file
not-a-structural-trace. Loosening this means loosening what a report may attach, so loosen the
FORMAT first and this after.

**@llmNote** A call line is taken apart with :meth:`str.index` and single-quantifier patterns rather
than matched by one regex. The obvious regex needs a nested quantifier for the dotted name, which is
both a backtracking hazard and a shape this repository's own SAST gate refuses on sight — and a
check that has to be excused by an exclusion is a check nobody trusts.
"""

from __future__ import annotations

import re
from typing import Final

_SEGMENT: Final = re.compile(r"\w+")
"""One identifier: a class name, a method name, a parameter name. No dot, by construction."""

_PARAMETERS: Final = re.compile(r"[\w, ]*")
"""The whole parameter list: names, commas and spaces. Never a colon, never a value."""

_HEADER: Final = re.compile(r"scenario: \S.*")

_MARKER_LINE: Final = re.compile(r" *~ (?:(?:fork|async) \[\d+\]|fire-and-forget)")
"""One of the published concurrency markers: ``~ fork [n]``, ``~ async [n]`` or
``~ fire-and-forget`` — nothing else that merely starts with ``~``."""

_LINE_END: Final = re.compile(r"\r\n|\r|\n")
"""Where a line ends: LF, CR or CRLF — the runtime's own reading. Splitting at LF alone let a
CR-only file hide every later line inside the header's."""

_SPAN_ID: Final = re.compile(r"( *)#[0-9]+(?:\.[0-9]+)* ")
"""A leading span id after the indent: ``#``, dot-separated ASCII digit runs, one space. Single
quantifiers on disjoint classes — no backtracking hazard."""

_BULLET: Final = "- "
_RETURNED: Final = " → value"
_INCOMPLETE: Final = " ?? incomplete"
_THREW: Final = " !! "


def looks_structural(content: str) -> bool:
    """Whether this content parses as a structural trace.

    Every line is right-stripped before it is read, so a LINE ENDING is not part of the grammar.
    The format is specified LF, and the tolerance is still the right answer: call lines were already
    stripped and marker lines were not, so a CRLF trace of nothing but calls parsed while the same
    trace with a ``~ fork [2]`` in it did not — and a Windows checkout with ``core.autocrlf=true``
    had a committed ``.approved.nt`` silently judged "not a structural trace" depending on whether
    its scenario happened to use concurrency. Leading whitespace is NOT stripped here: an indented
    header belongs to a different file shape.

    :raises TypeError: when ``content`` is ``None`` — an absent file is ``""``
    """
    if content is None:
        raise TypeError('the grammar check reads content, never None — an absent file is ""')
    header_seen = False
    for raw in _LINE_END.split(content):
        line = raw.rstrip()
        if not line:
            continue
        if not header_seen:
            header_seen = _HEADER.fullmatch(line) is not None
            if not header_seen:
                return False
        else:
            shape = _without_span_id(line)
            if not _is_call_line(shape) and _MARKER_LINE.fullmatch(shape) is None:
                return False
    return header_seen


def _without_span_id(line: str) -> str:
    """The line without the span id it may open with (``#1.3.2``, after the indent, then one
    space): a position path, so it carries no value. Anything after the indent that starts with
    ``#`` but is not a well-formed path is left in place, and then fails the line.

    **@llmNote** Mirrors ``narrativetrace.render.span_id.without_id``; this distribution sits below
    the core in the layering contract, so the grammar is restated rather than imported.
    """
    match = _SPAN_ID.match(line)
    return line if match is None else match.group(1) + line[match.end() :]


def _is_call_line(line: str) -> bool:
    """``- Type.method(a, b)`` plus at most one outcome marker."""
    bullet = line.strip()
    if not bullet.startswith(_BULLET):
        return False
    call = bullet[len(_BULLET) :]
    opened = call.find("(")
    closed = call.rfind(")")
    if opened < 0 or closed < opened:
        return False
    return (
        _is_dotted_name(call[:opened], 2)
        and _PARAMETERS.fullmatch(call[opened + 1 : closed]) is not None
        and _is_outcome(call[closed + 1 :])
    )


def _is_outcome(suffix: str) -> bool:
    """Nothing (a ``None``-shaped return), the returned marker, a thrown type, or incomplete."""
    if suffix in ("", _RETURNED, _INCOMPLETE):
        return True
    return suffix.startswith(_THREW) and _is_dotted_name(suffix[len(_THREW) :], 1)


def _is_dotted_name(name: str, minimum_segments: int) -> bool:
    """A dotted name of at least ``minimum_segments`` identifier segments."""
    segments = name.split(".")
    if len(segments) < minimum_segments:
        return False
    return all(_SEGMENT.fullmatch(segment) is not None for segment in segments)
