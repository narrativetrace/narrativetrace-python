# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property: span ids are a bijection with tree positions, and every flavour cites the same ids.

For any tree of plain calls, fork groups and fire-and-forget launches: the ``.nt`` gives every
call and every launch exactly one distinct id; an id's parent path is the id of the call or
launch it is nested under; indented text, Markdown and prose cite the same ids, each for the same
call (signatures are unique per node, so a line's call names its node). Order is not compared:
indented text and prose lay roots out in capture order, as the reference runtime does, so a root
fork or launch is printed in a different place — under the same ids.
"""

from __future__ import annotations

import itertools
import re

from hypothesis import given, settings
from hypothesis import strategies as st

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.structural import StructuralTraceRenderer
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

_ID = r"#\d+(?:\.\d+)*"
_NT_LINE = re.compile(rf"^( *)({_ID}) (?:- (C\d+)\.m\(|~ fire-and-forget$)")
_TRAILING_CALL = re.compile(rf"(C\d+|Launcher)\.(?:m|fire-and-forget)\*{{0,2}}\(.*? ({_ID})$")
_TRAILING_LAUNCH = re.compile(rf"⤳ fire-and-forget.* ({_ID})$")
_PROSE_ID = re.compile(rf"\(({_ID})\)")


def _trees() -> st.SearchStrategy[TraceTree]:
    """Unique class names (``C0``, ``C1`` …) so every call line names exactly one node."""

    def build(draw: st.DrawFn) -> TraceTree:
        counter = itertools.count()
        groups = itertools.count()

        def call(depth: int) -> TraceNode:
            children = siblings(depth + 1) if depth < 3 else []
            sig = MethodSignature(f"C{next(counter)}", "m", [])
            return TraceNode(sig, children, Returned("v"))

        def fork(depth: int) -> list[TraceNode]:
            info = ConcurrencyInfo(f"g{next(groups)}", ConcurrencyKind.FORK_JOIN)
            members = [call(depth) for _ in range(draw(st.integers(min_value=1, max_value=3)))]
            draw(st.randoms()).shuffle(members)
            return [
                TraceNode(m.signature, m.children, m.outcome, concurrency=info) for m in members
            ]

        def siblings(depth: int) -> list[TraceNode]:
            result: list[TraceNode] = []
            for kind in draw(st.lists(st.sampled_from(["call", "fork", "launch"]), max_size=3)):
                result.extend(fork(depth) if kind == "fork" else [make[kind](depth)])
            return result

        def launch(depth: int) -> TraceNode:
            info = ConcurrencyInfo(f"f{next(groups)}", ConcurrencyKind.FIRE_AND_FORGET)
            launched = siblings(depth + 1) if depth < 3 else []
            sig = MethodSignature("Launcher", "fire-and-forget", [])
            return TraceNode(sig, launched, None, concurrency=info)

        make = {"call": call, "launch": launch}

        return TraceTree(siblings(0))

    return st.composite(build)()


def _lines(tree: TraceTree) -> list[tuple[int, str | None, str | None]]:
    """(indent, id or None for a fork/async marker, class or None) for every ``.nt`` line."""
    rows: list[tuple[int, str | None, str | None]] = []
    for line in StructuralTraceRenderer().render(tree).splitlines():
        match = _NT_LINE.match(line)
        if match:
            rows.append((len(match.group(1)), match.group(2), match.group(3)))
        else:
            assert line.lstrip().startswith(("~ fork [", "~ async [")), line
            rows.append((len(line) - len(line.lstrip()), None, None))
    return rows


def _structural(tree: TraceTree) -> list[tuple[int, str, str | None]]:
    """(indent, id, class or None for a launch) for every id-bearing ``.nt`` line."""
    return [(indent, span, cls) for indent, span, cls in _lines(tree) if span is not None]


def _trailing(rendered: str) -> list[tuple[str, str | None]]:
    rows: list[tuple[str, str | None]] = []
    for line in rendered.splitlines():
        call = _TRAILING_CALL.search(line)
        launch = _TRAILING_LAUNCH.search(line)
        if call:
            rows.append((call.group(2), None if call.group(1) == "Launcher" else call.group(1)))
        elif launch:
            rows.append((launch.group(1), None))
    return rows


def _count(tree: TraceTree) -> int:
    def walk(nodes: list[TraceNode]) -> int:
        return sum(1 + walk(node.children) for node in nodes)

    return walk(tree.roots)


def _enclosing_ids(tree: TraceTree) -> list[tuple[str, str | None]]:
    """(span, id of the call or launch it is nested under) for every id-bearing line. A fork or
    async marker is transparent: its members nest one level deeper but belong to the call (or
    launch) that encloses the marker."""
    pairs: list[tuple[str, str | None]] = []
    open_lines: list[tuple[int, str | None]] = []
    for indent, span, _ in _lines(tree):
        while open_lines and open_lines[-1][0] >= indent:
            open_lines.pop()
        if span is not None:
            enclosing = [open_id for _, open_id in open_lines if open_id is not None]
            pairs.append((span, enclosing[-1] if enclosing else None))
        open_lines.append((indent, span))
    return pairs


def _parent_path(span: str) -> str | None:
    return span.rsplit(".", 1)[0] if "." in span else None


def _cited(rendered: str) -> list[tuple[str, str]]:
    return sorted((span, cls or "") for span, cls in _trailing(rendered))


@settings(max_examples=150, deadline=None)
@given(_trees())
def test_every_call_and_launch_has_one_distinct_id_nested_under_its_parents(
    tree: TraceTree,
) -> None:
    ids = [span for _, span, _ in _structural(tree)]

    assert len(ids) == _count(tree)
    assert len(set(ids)) == len(ids)
    for span, enclosing in _enclosing_ids(tree):
        assert _parent_path(span) == enclosing, span


@settings(max_examples=150, deadline=None)
@given(_trees())
def test_every_flavour_cites_the_same_span_for_the_same_call(tree: TraceTree) -> None:
    expected = sorted((span, cls or "") for _, span, cls in _structural(tree))
    # Indented text, like the reference runtime, prints a fork member below the roots as one
    # summary line without its subtree: what it prints must match, and what it omits must sit
    # under a span it printed — a summarized subtree, never a lost sibling.
    indented = _cited(IndentedTextRenderer().render(tree))
    assert set(indented) <= set(expected)
    printed = {span for span, _ in indented}
    omitted = {span for span, _ in set(expected) - set(indented)}
    assert all(any(s.startswith(f"{p}.") for p in printed) for s in omitted), omitted
    assert _cited(MarkdownRenderer().render(tree)) == expected
    prose = ProseRenderer().render(tree)
    assert sorted(_PROSE_ID.findall(prose)) == [span for span, _ in expected]
