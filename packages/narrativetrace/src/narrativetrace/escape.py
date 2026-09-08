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


def control_sanitize(text: str) -> str:
    """Renders every control character and surrogate code point as an inert escape, leaving
    quotes/backslashes intact.

    Common controls map to ``\\n``/``\\r``/``\\t``/``\\b``/``\\f`` mnemonics; every other ISO
    control code point, and every surrogate code point (a security fuzz suite finding, mirrors
    Java's ``ControlEscape`` fix), maps to ``\\uXXXX``. Quotes and backslashes are legitimate
    value content and pass through unchanged.

    A surrogate is not a control character, but no UTF-8 sink can encode it either -- and unlike
    Java's UTF-16-backed ``String``, a Python ``str`` never holds a well-formed astral character
    as an adjacent surrogate pair (``json.loads`` already merges one into a single code point at
    parse time), so every surrogate this function sees is escaped unconditionally; there is no
    paired-surrogate case to special-case around.
    """
    out: list[str] = []
    for char in text:
        codepoint = ord(char)
        mnemonic = _MNEMONICS.get(char)
        if mnemonic is not None:
            out.append(mnemonic)
        elif _is_iso_control(codepoint) or _is_surrogate(codepoint):
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
    lines to the document -- structure the injection-containment oracle forbids), mirroring
    Java's ``MarkdownEscape.text()``.
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

    ``content`` is control-sanitised first (mirrors Java's ``MarkdownEscape.code()``) so a raw
    line break cannot end the span early either. When the fence is widened, one space of padding
    is added on each side (CommonMark strips a single leading/trailing space), keeping the
    content faithful. Content with no backtick is wrapped in a single-backtick span.
    """
    content = control_sanitize(content)
    max_run = _longest_backtick_run(content)
    if max_run == 0:
        return f"`{content}`"
    fence = "`" * (max_run + 1)
    return f"{fence} {content} {fence}"
