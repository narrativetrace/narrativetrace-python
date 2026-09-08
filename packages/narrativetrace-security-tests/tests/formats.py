# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Structural (shape) comparisons for the injection-containment oracle.

The shape-comparison half of the shared ``Formats`` oracle -- well-formedness itself (schema
validation, YAML frontmatter parsing) already lives in the root ``conformance.py`` module and
``test_output_format_properties.py``. What lives here answers a narrower question: given two
renders of the *same tree shape*, did one of them add structure the other doesn't have? An
injection payload that stayed one value produces the same shape as a benign value in the same
position, whatever it contained; a payload that broke out of its string produces a different one
-- an extra JSON field, an extra diagram statement, a forged frontmatter key, an extra fence.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

_HEADING_LINE = re.compile(r"#{1,6} .*")


def json_shape(document: object) -> str:
    """The document's shape with every scalar's content erased: field names, array lengths and
    node kinds only. Comparing shapes says "exactly one value" without having to guess where in
    the document that value sits."""
    parts: list[str] = []
    _append_shape(document, parts)
    return "".join(parts)


def _append_shape(node: object, parts: list[str]) -> None:
    if isinstance(node, dict):
        parts.append("{")
        for key, value in node.items():
            parts.append(f"{key}:")
            _append_shape(value, parts)
            parts.append(",")
        parts.append("}")
    elif isinstance(node, list):
        parts.append("[")
        for element in node:
            _append_shape(element, parts)
        parts.append("]")
    else:
        parts.append(type(node).__name__)


def statements_of(diagram: str) -> list[str]:
    """The statement lines of a diagram: header line skipped, blank lines and ``%%`` comments
    filtered, indentation stripped."""
    lines = diagram.splitlines()[1:]
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("%%")]


def fence_count(markdown: str) -> int:
    """How many fenced-code delimiters a Markdown document carries."""
    return sum(1 for line in markdown.splitlines() if line.strip().startswith("```"))


def frontmatter_fence_count(markdown: str) -> int:
    """How many frontmatter fences a Markdown document carries: exactly two, or it is broken."""
    return sum(1 for line in markdown.splitlines() if line.strip() == "---")


def heading_count(markdown: str) -> int:
    """How many ATX heading lines a Markdown document carries.

    A heading is document structure the renderer alone may write; a value or a scenario that
    adds one has forged the document's outline (a 2026-09-08 audit in the Java spec repo caught
    exactly that through the body header's raw scenario).
    """
    return sum(1 for line in markdown.splitlines() if _HEADING_LINE.fullmatch(line))


def frontmatter_keys(markdown: str) -> set[str]:
    """The YAML frontmatter block's top-level key set."""
    lines = markdown.splitlines()
    end = lines.index("---", 1)
    block = "\n".join(lines[1:end])
    parsed: Any = yaml.safe_load(block)
    return set(parsed) if parsed else set()


def strings_named(node: object, field_name: str) -> list[str]:
    """Every string value under ``node`` whose key is ``field_name``, in document order -- the
    strongest form of "it came back as exactly one value": the bytes match, and they are one
    node."""
    found: list[str] = []
    _collect_strings(node, field_name, found)
    return found


def _collect_strings(node: object, field_name: str, found: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == field_name and isinstance(value, str):
                found.append(value)
            _collect_strings(value, field_name, found)
    elif isinstance(node, list):
        for element in node:
            _collect_strings(element, field_name, found)
