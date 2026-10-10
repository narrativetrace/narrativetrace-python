# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The citable id of one span in a rendered trace: its position path in the tree, ``#1``,
``#1.3``, ``#1.3.2`` (root call, its third child, that child's second child).

An agent's report, a grader, an approval delta and a human review must be able to point at the
same span. The id is DERIVED from the tree by the renderer — never stored in the event stream,
never random — so two runs of the same flow give the same ids, and every flavour prints the same
id for the same span (``documentation/structural-trace-format.md``, "Span ids").

Numbering rule, shared by every renderer: a sibling list (a tree's roots, one node's children, a
fire-and-forget launcher's launched work) is numbered segment by segment
(:func:`~narrativetrace.render.concurrency.partition`). A plain call takes one position; a fork
or async group takes one position per member, given in :func:`concurrent_order` (by
``Class.method`` — capture order across threads is the scheduler's, so it can number nothing); a
fire-and-forget launch takes ONE position, and the work it launched nests under that id.
"""

from __future__ import annotations

from narrativetrace.nodes import TraceNode
from narrativetrace.render.concurrency import partition

_DIGITS = frozenset("0123456789")
_RANGE_DASH = "\u2013"
"""The en dash a citation of a run of ids is joined with: ``#1.2\u2013#1.4``."""


def concurrent_order(node: TraceNode) -> str:
    """The sort key members of one fork or async group take their ids in: ``Class.method``, the
    order the structural trace prints them in. Python's sort is stable, so equal signatures keep
    capture order."""
    return f"{node.signature.class_name}.{node.signature.method_name}"


def child(parent: str | None, position: int) -> str:
    """The id of a child at a 1-based ``position`` under ``parent``; a root when ``parent`` is
    ``None``."""
    return f"#{position}" if parent is None else f"{parent}.{position}"


class SpanCursor:
    """Hands out the ids of one sibling list in the order a renderer plans it.

    Every tree renderer plans a sibling list segment by segment — a plain call, a fork's members
    in :func:`concurrent_order`, a fire-and-forget launcher — and that planning order IS the id
    order. Taking the next id at the moment a span is planned keeps the numbering in one place
    instead of an offset threaded through every renderer.
    """

    def __init__(self, parent: str | None) -> None:
        self._parent = parent
        self._position = 0

    def next(self) -> str:
        """The id of the next sibling in planning order."""
        self._position += 1
        return child(self._parent, self._position)


def ids_of(siblings: list[TraceNode], parent: str | None) -> list[str]:
    """The id of every node in ``siblings``, index for index — for a renderer that walks them in
    capture order rather than in the order ids are given in (the sequence diagrams).

    Args:
        siblings: one node's children, or a tree's roots.
        parent: the id of the node they belong to; ``None`` for roots.
    """
    ids: list[str] = []
    cursor = SpanCursor(parent)
    for segment in partition(siblings):
        if segment.is_fire_and_forget():
            ids.append(cursor.next())
            continue
        ranked = sorted(range(len(segment.nodes)), key=lambda i: concurrent_order(segment.nodes[i]))
        segment_ids = [""] * len(segment.nodes)
        for index in ranked:
            segment_ids[index] = cursor.next()
        ids.extend(segment_ids)
    return ids


def cite_range(ids: list[str]) -> str:
    """A run of consecutive sibling ids as one citation — first and last joined by
    :data:`_RANGE_DASH` — or the id itself when the run is one span long.

    Raises:
        ValueError: when ``ids`` is empty — an empty run cites nothing.
    """
    if not ids:
        raise ValueError("a range cites at least one span")
    return ids[0] if len(ids) == 1 else f"{ids[0]}{_RANGE_DASH}{ids[-1]}"


def without_id(line: str) -> str:
    """``line`` without its leading span id: ``"  #1.2 - A.b()"`` becomes ``"  - A.b()"``.

    A line that carries no well-formed id — a marker, a header, a baseline written before ids
    existed — is returned unchanged, which is what lets an id-free ``.approved.nt`` still compare.
    """
    start = _indent_of(line)
    end = _id_end(line, start)
    return line if end is None else line[:start] + line[end + 1 :]


def of(line: str) -> str | None:
    """The span id ``line`` opens with (after its space indent), or ``None`` when it carries
    none."""
    start = _indent_of(line)
    end = _id_end(line, start)
    return None if end is None else line[start:end]


def is_well_formed(text: str | None) -> bool:
    """Whether ``text`` is exactly one span id: ``#``, then dot-separated runs of ASCII digits."""
    return text is not None and _id_end(text + " ", 0) == len(text)


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _id_end(line: str, start: int) -> int | None:
    """Index of the space that ends an id starting at ``start``, or ``None`` when no well-formed
    id is there (``#``, dot-separated runs of ASCII digits, then one ASCII space)."""
    if not line.startswith("#", start):
        return None
    digits_in_run = 0
    for index in range(start + 1, len(line)):
        char = line[index]
        if char in _DIGITS:
            digits_in_run += 1
        elif char == "." and digits_in_run > 0:
            digits_in_run = 0
        else:
            return index if char == " " and digits_in_run > 0 else None
    return None
