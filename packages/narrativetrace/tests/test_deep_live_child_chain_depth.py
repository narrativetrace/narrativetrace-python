# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-198 (Python twin of Java ``DeepLiveChildChainDepthTest``): a worker that holds many async
scopes open, each activated from a snapshot of the one before, builds a chain of live children.
Reading the chain recursed once per link with no bound, so the origin's own ``capture_trace()``,
the hand-over at scope close and ``reset()`` all raised ``RecursionError`` into the host.

Every link lives in its own ``contextvars.Context`` so the scopes can stay open and close in any
order, exactly as a registry of scope handles would close them.
"""

from __future__ import annotations

import contextvars
from contextlib import AbstractContextManager

import pytest

from narrativetrace.context import MAX_LIVE_CHILD_DEPTH, ContextVarNarrativeContext
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature

_DEEP = 5_000
_ORIGIN_CALL = MethodSignature("Origin", "call", [])
_STEP = MethodSignature("Worker", "step", [])


class _Link:
    """One open scope: its own execution context, entered and exited inside it."""

    def __init__(self, context: contextvars.Context, scope: AbstractContextManager[None]) -> None:
        self.context = context
        self.scope = scope

    def close(self) -> None:
        self.context.run(self.scope.__exit__, None, None, None)


def _open_chain(
    ctx: ContextVarNarrativeContext, links: int, *, call_each: bool = False
) -> list[_Link]:
    chain: list[_Link] = []
    current = contextvars.copy_context()
    for _ in range(links):
        link_context = current.copy()
        scope = link_context.run(lambda: ctx.snapshot().activate())
        link_context.run(scope.__enter__)
        if call_each:
            link_context.run(ctx.enter_method, _STEP)
            link_context.run(ctx.exit_method_with_return, "null")
        chain.append(_Link(link_context, scope))
        current = link_context
    return chain


def _steps(ctx: ContextVarNarrativeContext) -> int:
    def walk(nodes: list[TraceNode]) -> int:
        return sum(
            (1 if node.signature.method_name == "step" else 0) + walk(node.children)
            for node in nodes
        )

    return walk(ctx.capture_trace().roots)


@pytest.fixture
def ctx() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext()


class TestADeepChainOfOpenAsyncScopes:
    def test_the_origin_captures_its_own_trace_with_thousands_of_scopes_open(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_ORIGIN_CALL)
        chain = _open_chain(ctx, _DEEP)
        try:
            ctx.capture_trace()
        finally:
            for link in reversed(chain):
                link.close()

    def test_closing_a_deep_chain_oldest_first_does_not_overflow_the_worker(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_ORIGIN_CALL)
        chain = _open_chain(ctx, _DEEP)

        for link in chain:
            link.close()

    def test_resetting_the_origin_under_a_deep_chain_does_not_overflow(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_ORIGIN_CALL)
        chain = _open_chain(ctx, _DEEP)

        ctx.reset()
        for link in chain:
            link.close()

    def test_work_past_the_depth_cap_is_invisible_while_open_and_handed_over_whole_at_close(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        links = MAX_LIVE_CHILD_DEPTH + 1
        ctx.enter_method(_ORIGIN_CALL)
        chain = _open_chain(ctx, links, call_each=True)

        assert _steps(ctx) == links - 1, "the link past the cap is not visible while open"

        for link in reversed(chain):
            link.close()

        assert _steps(ctx) == links, "and arrives whole at close"
