# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Escapers for text bound for line-oriented, terminal, and Markdown sinks.

``ControlEscape`` and ``MarkdownEscape``. Rendered values, exception messages, and
error context flow into logs, a console renderer, and Markdown documents; these helpers are the
single places that neutralise characters capable of forging log lines (CWE-117), injecting ANSI
sequences, or introducing active Markdown/HTML.
"""

from __future__ import annotations

_MNEMONICS = {
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def _is_iso_control(codepoint: int) -> bool:
    return codepoint <= 0x1F or 0x7F <= codepoint <= 0x9F


def _is_surrogate(codepoint: int) -> bool:
    return 0xD800 <= codepoint <= 0xDFFF


def _is_line_separator(codepoint: int) -> bool:
    """U+2028 and U+2029: not ISO controls, but line terminators to regex engines, JavaScript and
    many log viewers, so a raw one forges a line exactly as ``\\n`` does."""
    return codepoint in (0x2028, 0x2029)


def control_sanitize(text: str) -> str:
    """Renders every control character and surrogate code point as an inert escape, leaving
    quotes/backslashes intact.

    Common controls map to ``\\n``/``\\r``/``\\t``/``\\b``/``\\f`` mnemonics; every other ISO
    control code point, every surrogate code point (a security fuzz suite finding), and the Unicode
    line and paragraph separators U+2028/U+2029 map to ``\\uXXXX``. Quotes and backslashes are
    legitimate value content and pass through unchanged.

    A surrogate is not a control character, but no UTF-8 sink can encode it either -- and a Python
    ``str`` never holds a well-formed astral character as an adjacent surrogate pair
    (``json.loads`` already merges one into a single code point at parse time), so every surrogate
    this function sees is escaped unconditionally; there is no paired-surrogate case to
    special-case around.
    """
    out: list[str] = []
    for char in text:
        codepoint = ord(char)
        mnemonic = _MNEMONICS.get(char)
        if mnemonic is not None:
            out.append(mnemonic)
        elif (
            _is_iso_control(codepoint) or _is_surrogate(codepoint) or _is_line_separator(codepoint)
        ):
            out.append(f"\\u{codepoint:04x}")
        else:
            out.append(char)
    return "".join(out)


def markdown_text(text: str) -> str:
    """Neutralises control characters, then HTML-escapes ``&``, ``<``, ``>`` so interpolated
    prose (an exception message, narration, error context -- any of which may carry
    attacker-influenced content) cannot introduce active HTML or break out of the single line
    it was interpolated into.

    Control characters are sanitised first (security fuzz suite finding: an exception message
    carrying a raw newline plus a frontmatter/fence delimiter added extra ``---``/```` ``` ````
    lines to the document -- structure the injection-containment oracle forbids).
    """
    safe = control_sanitize(text)
    return safe.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _longest_backtick_run(text: str) -> int:
    longest = 0
    run = 0
    for char in text:
        if char == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return longest


def markdown_code(content: str) -> str:
    """Wraps ``content`` in a backtick code span whose fence is longer than any run inside it.

    ``content`` is control-sanitised first, so a raw line break cannot end the span early either.
    When the fence is widened, one space of padding
    is added on each side (CommonMark strips a single leading/trailing space), keeping the
    content faithful. Content with no backtick is wrapped in a single-backtick span.
    """
    content = control_sanitize(content)
    max_run = _longest_backtick_run(content)
    if max_run == 0:
        return f"`{content}`"
    fence = "`" * (max_run + 1)
    return f"{fence} {content} {fence}"


def collapse_line_breaks(text: str) -> str:
    """Replaces each ``\\r\\n``, ``\\n`` or ``\\r`` with one space, so one value stays one line.

    The prose form of the shared Markdown cell escape: headings, header lines and console
    pointers use it directly; table cells use :func:`markdown_table_cell`.
    """
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def markdown_table_cell(text: str) -> str:
    """Escapes ``\\`` and ``|`` and collapses line breaks so ``text`` stays inside one table cell.

    The backslash is escaped first: a ``\\`` already in ``text`` would otherwise pair with the
    escape added for a ``|`` after it, leaving the pipe live and splitting the row. Pass raw text,
    never text that is already escaped. The one table-cell escape for every Markdown table
    NarrativeTrace writes (the glossary view and the clarity report).
    """
    return collapse_line_breaks(text.replace("\\", "\\\\").replace("|", "\\|"))


def markdown_code_span_cell(text: str) -> str:
    """Renders ``text`` as a code span that stays inside one table cell.

    Line breaks collapse, ``|`` becomes ``%7C`` and a backtick becomes ``%60``: a backslash has no
    power inside a code span, so a backslash escape would show literally and a ``|`` would still
    end the cell. Backslashes are kept as they are. Pass raw text.
    """
    return markdown_code(collapse_line_breaks(text).replace("|", "%7C").replace("`", "%60"))
