# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""D8: every flavour cites every span by the same id — indented text and Markdown as a trailing
``#id``, prose as ``(#id)``. The ``.nt`` column is pinned in ``test_structural.py``; the diagrams'
notes in the diagrams package.
"""

from __future__ import annotations

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned, Threw, TraceOutcome
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.structural import StructuralTraceRenderer
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

_FORK = ConcurrencyInfo("g", ConcurrencyKind.FORK_JOIN, thread_name="t")
_LAUNCH = ConcurrencyInfo("f", ConcurrencyKind.FIRE_AND_FORGET, thread_name="bg")


def _node(
    class_name: str,
    method_name: str,
    outcome: TraceOutcome | None = None,
    children: list[TraceNode] | None = None,
    concurrency: ConcurrencyInfo | None = None,
) -> TraceNode:
    return TraceNode(
        signature=MethodSignature(class_name, method_name, []),
        children=children or [],
        outcome=outcome if outcome is not None or concurrency is _LAUNCH else Returned(None),
        concurrency=concurrency,
    )


def _flow() -> TraceTree:
    """A root with a plain child, a two-member fork in reverse signature order, a launched
    background call and a failing leaf; then a second root."""
    return TraceTree(
        [
            _node(
                "Orders",
                "place",
                children=[
                    _node("Stock", "check"),
                    _node("Pay", "charge", concurrency=_FORK),
                    _node("Mail", "send", concurrency=_FORK),
                    _node(
                        "Orders",
                        "launch",
                        children=[_node("Audit", "log")],
                        concurrency=_LAUNCH,
                    ),
                    _node("Ledger", "post", Threw(ValueError("closed"))),
                ],
            ),
            _node("Orders", "report"),
        ]
    )


def _body(rendered: str) -> str:
    """The render without its ``trace:`` header — the trace's own random name."""
    return rendered.split("\n\n", 1)[1]


class TestIndentedText:
    def test_every_span_line_ends_with_its_id(self) -> None:
        assert _body(IndentedTextRenderer().render(_flow())) == (
            "Orders.place() #1\n"
            "├── Stock.check() → null #1.1\n"
            "├── ⑂ fork [2 tasks]\n"
            "│   ├── ↦ Mail.send() → null #1.2\n"
            "│   │       [thread: t] [async, awaited sequentially]\n"
            "│   ├── ↦ Pay.charge() → null #1.3\n"
            "│   │       [thread: t] [async, awaited sequentially]\n"
            "├── ⑃ join — 0ms\n"
            "├── ⚡ Sequential async: total 0ms, parallelizable to ~0ms\n"
            "├── ⤳ fire-and-forget [thread: bg] #1.4\n"
            "│   ├── Audit.log() → null #1.4.1\n"
            "├── Ledger.post() !! ValueError: closed #1.5\n"
            "└── → null\n"
            "Orders.report() → null #2"
        )


class TestMarkdown:
    def test_every_span_line_ends_with_its_id_and_a_throw_cites_before_its_block(self) -> None:
        assert MarkdownRenderer().render(_flow()) == (
            "- **Orders.place**() #1\n"
            "  - **Stock.check**() → `null` #1.1\n"
            "  - ⑂ fork [2 tasks]\n"
            "    - ↦ **Mail.send**() → `null` #1.2\n"
            "          [thread: t] [async, awaited sequentially]\n"
            "    - ↦ **Pay.charge**() → `null` #1.3\n"
            "          [thread: t] [async, awaited sequentially]\n"
            "  - ⑃ join — 0ms\n"
            "  - ⚡ Sequential async: total 0ms, parallelizable to ~0ms\n"
            "  - ⤳ fire-and-forget [thread: bg] #1.4\n"
            "    - **Audit.log**() → `null` #1.4.1\n"
            "  - **Ledger.post**() #1.5\n"
            "\n"
            "    > ❌ `ValueError`: closed\n"
            "  - → `null`\n"
            "- **Orders.report**() → `null` #2"
        )


class TestProse:
    def test_every_sentence_cites_its_span_in_parentheses(self) -> None:
        assert _body(ProseRenderer().render(_flow())) == (
            "The orders place (#1):\n"
            "  The stock check (#1.1).\n"
            "  Concurrently:\n"
            "    The mail send (#1.2).\n"
            "    The pay charge (#1.3).\n"
            "    (Note: tasks ran sequentially — total 0ms, parallelizable to ~0ms.)\n"
            "  In the background (#1.4):\n"
            "    The audit log (#1.4.1).\n"
            "  The ledger failed to post (#1.5) — ValueError: closed.\n"
            "The orders report (#2)."
        )


class TestLaunchedWorkLaysOutLikeAnySiblingList:
    """A fork inside fire-and-forget work keeps its marker and its members their own ids."""

    def _launched_fork(self) -> TraceTree:
        launcher = _node(
            "Orders",
            "launch",
            children=[
                _node("Pay", "charge", concurrency=_FORK),
                _node("Mail", "send", concurrency=_FORK),
            ],
            concurrency=_LAUNCH,
        )
        return TraceTree([_node("Orders", "place", children=[launcher])])

    def test_indented_text(self) -> None:
        rendered = IndentedTextRenderer().render(self._launched_fork())
        assert "│   ├── ⑂ fork [2 tasks]\n│   │   ├── ↦ Mail.send() → null #1.1.1\n" in rendered

    def test_markdown(self) -> None:
        rendered = MarkdownRenderer().render(self._launched_fork())
        assert "    - ⑂ fork [2 tasks]\n      - ↦ **Mail.send**() → `null` #1.1.1\n" in rendered

    def test_prose(self) -> None:
        rendered = ProseRenderer().render(self._launched_fork())
        assert "    Concurrently:\n      The mail send (#1.1.1).\n" in rendered


class TestLaunchersGoThroughTheWalk:
    """A fire-and-forget launcher is a node of the tree like any other: a launcher already on the
    path, or one past the depth limit, gets its marker and is not descended into — in every
    flavour (adversarial pass: a self-launching cycle recursed forever, and a long chain of
    launchers raised RecursionError, because launched work bypassed the walk)."""

    def _cycle(self) -> TraceTree:
        loop = _node("Orders", "launch", children=[], concurrency=_LAUNCH)
        loop.children.append(loop)
        return TraceTree([_node("Orders", "place", children=[loop])])

    def test_the_structural_trace_marks_the_cycle_on_the_launch_line(self) -> None:
        assert StructuralTraceRenderer().render(self._cycle()) == (
            "#1 - Orders.place()\n"
            "  #1.1 ~ fire-and-forget\n"
            "    #1.1.1 ~ fire-and-forget … (cycle)\n"
        )

    def test_indented_text_markdown_and_prose_mark_it_too(self) -> None:
        tree = self._cycle()
        assert "│   ├── ⤳ fire-and-forget [thread: bg] … (cycle) #1.1.1\n" in (
            IndentedTextRenderer().render(tree)
        )
        assert "    - ⤳ fire-and-forget [thread: bg] … (cycle) #1.1.1\n" in (
            MarkdownRenderer().render(tree)
        )
        assert ProseRenderer().render(tree).endswith("    In the background (#1.1.1) … (cycle).")

    def test_a_chain_of_launchers_stops_at_the_depth_limit(self) -> None:
        node = _node("Orders", "launch", children=[], concurrency=_LAUNCH)
        for _ in range(599):
            node = _node("Orders", "launch", children=[node], concurrency=_LAUNCH)
        tree = TraceTree([_node("Orders", "place", children=[node])])
        for renderer in (
            StructuralTraceRenderer(),
            IndentedTextRenderer(),
            MarkdownRenderer(),
            ProseRenderer(),
        ):
            assert "… (depth limit)" in renderer.render(tree)
