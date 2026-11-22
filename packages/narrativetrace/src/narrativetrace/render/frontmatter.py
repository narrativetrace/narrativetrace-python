# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""YAML frontmatter for Markdown trace documents.

``FrontmatterBuilder``.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Threw
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk

_YAML_INDICATOR_LEADERS = frozenset("-?:,[]{}#&*!|>'\"%@`")
"""Characters a YAML plain scalar cannot start with (security fuzz suite finding: an unquoted
scenario starting with e.g. ``%`` is not a directive, it is a scalar, but the reader cannot tell
without a quote)."""

_YAML_NONCHARACTERS = chr(0xFFFE) + chr(0xFFFF)
"""The two BMP noncharacters YAML's own printable-character rule excludes from its otherwise
unrestricted private-use range (``U+E000``-``U+FFFD``) -- outside ``control_sanitize``'s
definition of a control character, since they are not one, but still not raw-YAML-safe."""


def yaml_safe(value: str) -> str:
    """Quotes/escapes a scenario value that would otherwise break or be misread as YAML."""
    if _needs_quoting(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = control_sanitize(escaped)
        escaped = "".join(f"\\u{ord(c):04x}" if c in _YAML_NONCHARACTERS else c for c in escaped)
        escaped = _escape_supplementary(escaped)
        return f'"{escaped}"'
    return value


def _escape_supplementary(text: str) -> str:
    """Every code point above the Basic Multilingual Plane becomes an 8-digit ``\\U`` escape.

    A Python ``str`` already holds a supplementary character as one code point, and PyYAML
    round-trips it raw without incident -- there is no
    surrogate-pair encoding here for a downstream reader's buffer boundary to split. But
    frontmatter is a machine-readable interoperability contract this runtime shares with every
    other NarrativeTrace runtime (some YAML readers crash on supplementary characters), so it is
    kept BMP-only here too: ``\\U`` is YAML's own 32-bit escape (``ns-esc-32-bit``), and a
    conforming parser anywhere decodes it back to the same code point.
    """
    return "".join(f"\\U{ord(c):08x}" if ord(c) > 0xFFFF else c for c in text)


_YAML_RETYPED_WORDS = frozenset(
    ("true", "false", "yes", "no", "on", "off", "y", "n", "null", "~", ".inf", ".nan")
)
"""Case-folded words a YAML 1.1 reader resolves to a boolean, null or float rather than a string."""

_DIGITS = frozenset("0123456789")
_HEX_DIGITS = frozenset("0123456789abcdef")
_BINARY_DIGITS = frozenset("01")


def _all_in(text: str, alphabet: frozenset[str]) -> bool:
    return bool(text) and all(c in alphabet for c in text.replace("_", ""))


def _is_digit_run(text: str, shortest: int, longest: int) -> bool:
    return shortest <= len(text) <= longest and all(c in _DIGITS for c in text)


def _is_timestamp(value: str) -> bool:
    """``YYYY-M-D`` alone or followed by a ``T``/``t``/space time part -- a conservative cover
    of every YAML 1.1 timestamp form. One left-to-right pass, no backtracking."""
    year, _, rest = value.partition("-")
    month, _, rest = rest.partition("-")
    day_length = len(rest) - len(rest.lstrip("0123456789"))
    day, tail = rest[:day_length], rest[day_length:]
    return (
        _is_digit_run(year, 4, 4)
        and _is_digit_run(month, 1, 2)
        and _is_digit_run(day, 1, 2)
        and (not tail or tail[0] in "Tt \t")
    )


def _is_decimal_number(body: str) -> bool:
    """An integer (decimal, leading-zero octal) or a fixed/exponent float, ``_`` allowed."""
    mantissa, has_exponent, exponent = body.partition("e")
    if has_exponent and not _all_in(exponent.removeprefix("+").removeprefix("-"), _DIGITS):
        return False
    whole, dot, fraction = mantissa.partition(".")
    if not (whole[:1] in _DIGITS or (dot and not whole)):
        return False
    return _all_in(whole + fraction, _DIGITS)


def _is_number(value: str) -> bool:
    body = value.removeprefix("+").removeprefix("-")
    if body[:2] in ("0x", "0b"):
        return _all_in(body[2:], _HEX_DIGITS if body[1] == "x" else _BINARY_DIGITS)
    return _is_decimal_number(body)


def _resolves_to_non_string(value: str) -> bool:
    """True when a YAML 1.1 reader would read the bare ``value`` as a boolean, null, integer,
    float or timestamp, so the value must be quoted to stay a string."""
    folded = value.lower()
    body = folded.lstrip("+-") if folded[:1] in ("+", "-") else folded
    return (
        folded in _YAML_RETYPED_WORDS
        or body == ".inf"
        or _is_timestamp(folded)
        or _is_number(folded)
    )


def _needs_quoting(value: str) -> bool:
    if not value or value != value.strip() or value[0] in _YAML_INDICATOR_LEADERS:
        return True
    if _resolves_to_non_string(value) or any(c in value for c in ':#"\\\n'):
        return True
    return _has_unprintable(value)


def _has_unprintable(value: str) -> bool:
    if any(c in _YAML_NONCHARACTERS for c in value) or any(ord(c) > 0xFFFF for c in value):
        return True
    # control_sanitize is a no-op on a string with no control character or surrogate to escape --
    # reusing it here means "does this need a \n/\uXXXX escape" never drifts from the one place
    # that defines what a control character is.
    return control_sanitize(value) != value


def _count_nodes(node: TraceNode, walk: TreeWalk | None = None) -> int:
    walk = walk if walk is not None else TreeWalk()
    total = 1
    if walk.stop_reason(node) is None:
        walk.enter(node)
        try:
            total += sum(_count_nodes(child, walk) for child in node.children)
        finally:
            walk.exit(node)
    return total


def _count_errors(node: TraceNode, walk: TreeWalk | None = None) -> int:
    walk = walk if walk is not None else TreeWalk()
    own = 1 if isinstance(node.outcome, Threw) else 0
    if walk.stop_reason(node) is None:
        walk.enter(node)
        try:
            own += sum(_count_errors(child, walk) for child in node.children)
        finally:
            walk.exit(node)
    return own


def _append_root_fields(tree: TraceTree, lines: list[str]) -> None:
    """``entry_point``, ``duration_ms`` and, when the root carries one, ``trace_id``/
    ``trace_name`` -- appends nothing on an empty tree. Split out of
    :meth:`FrontmatterBuilder.build` to keep it under the method-length gate once the run field's
    two lines landed there (mirrors the reference runtime's identical extraction)."""
    if not tree.roots:
        return
    root = tree.roots[0]
    sig = root.signature
    entry_point = f"{sig.class_name}.{sig.method_name}"
    lines.append(f"entry_point: {yaml_safe(entry_point)}")
    lines.append(f"duration_ms: {root.duration_millis}")
    if root.span_context is not None:
        trace_id = root.span_context.trace_id
        lines.append(f"trace_id: {yaml_safe(trace_id.value)}")
        lines.append(f"trace_name: {trace_id.human_name()}")


class FrontmatterBuilder:
    """Builds the YAML frontmatter block for a trace document."""

    def __init__(self) -> None:
        self._scenario: str | None = None
        self._run_name: str | None = None

    def scenario(self, scenario: str) -> FrontmatterBuilder:
        """Sets the scenario line; returns self for chaining."""
        self._scenario = scenario
        return self

    def run_name(self, run_name: str | None) -> FrontmatterBuilder:
        """Sets the enclosing test-suite run's three-word phrase (2026-09-13 ruling, item 2);
        returns self for chaining. ``None`` (the default) omits the field entirely — a document
        rendered outside a tracked run names no run.

        This is the ONLY frontmatter field a
        :class:`~narrativetrace.output.run_identity.RunIdentity` ever reaches: never folded into
        ``scenario``, never read back by ``entry_point``/``trace_id``/``trace_name``, and never
        present on the structural ``.nt`` artifact at all (item 3).
        """
        self._run_name = run_name
        return self

    def build(self, tree: TraceTree) -> str:
        """Renders the frontmatter block (delimited by ``---`` lines)."""
        lines = ["---", "type: trace"]
        if self._run_name is not None:
            lines.append(f"run: {yaml_safe(self._run_name)}")
        if self._scenario is not None:
            lines.append(f"scenario: {yaml_safe(self._scenario)}")
        _append_root_fields(tree, lines)
        method_count = sum(_count_nodes(root) for root in tree.roots)
        error_count = sum(_count_errors(root) for root in tree.roots)
        lines.append(f"method_count: {method_count}")
        lines.append(f"error_count: {error_count}")
        lines.append("---")
        return "\n".join(lines) + "\n"
