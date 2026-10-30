# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-199 (Python twin of Java ``MalformedGraftedNodeTest``): grafting a malformed node may neither
raise into the traced application nor leave the caller's own span half-open.

``emit_trace_node`` published the enter and pushed the grafted span onto the CALLER's active stack
before it could discover the node was unusable, so the caller's next exit popped the graft: the
host method was recorded ``Incomplete`` and its return value landed on the grafted span. The whole
graft is now validated by one bounded walk first; a malformed one is dropped whole, with one
stderr line, and the caller's span is never touched.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned
from narrativetrace.signature import MethodSignature

_ORIGIN = MethodSignature("OrderService", "placeOrder", [])
_GRAFTED = MethodSignature("EmailGateway", "send", [])


def _node(*, signature: Any = _GRAFTED, children: Any = None) -> TraceNode:
    return TraceNode(signature, [] if children is None else children, Returned("ok"))


def _malformed() -> dict[str, TraceNode]:
    no_children = _node()
    object.__setattr__(no_children, "children", None)
    no_signature = _node(signature=None)
    return {
        "null-child-list": no_children,
        "null-signature": no_signature,
        "null-child-in-list": _node(children=[None]),
        "malformed-grandchild": _node(children=[_node(children=[no_children])]),
    }


@pytest.fixture
def ctx() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext()


@pytest.mark.parametrize("kind", list(_malformed()))
class TestAMalformedGraft:
    def test_never_raises_into_the_caller(self, ctx: ContextVarNarrativeContext, kind: str) -> None:
        ctx.enter_method(_ORIGIN)
        span = ctx.current_span_id()

        ctx.emit_trace_node(_malformed()[kind], span)

    def test_leaves_the_callers_own_span_balanced(
        self, ctx: ContextVarNarrativeContext, kind: str
    ) -> None:
        ctx.enter_method(_ORIGIN)
        span = ctx.current_span_id()
        # "never raises" is the other test's concern; this one owns the stranded span
        with contextlib.suppress(Exception):
            ctx.emit_trace_node(_malformed()[kind], span)

        ctx.exit_method_with_return("done")

        roots = ctx.capture_trace().roots
        assert [r.signature.method_name for r in roots] == ["placeOrder"]
        assert isinstance(roots[0].outcome, Returned)
        assert roots[0].outcome.rendered_value == "done"
        assert not isinstance(roots[0].outcome, Incomplete)
        assert roots[0].children == []

    def test_says_so_once_on_stderr(
        self, ctx: ContextVarNarrativeContext, kind: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ctx.enter_method(_ORIGIN)
        with contextlib.suppress(Exception):
            ctx.emit_trace_node(_malformed()[kind], ctx.current_span_id())

        assert capsys.readouterr().err.count("narrative-trace: emit_trace_node dropped") == 1


def test_a_well_formed_graft_is_still_replayed_whole(ctx: ContextVarNarrativeContext) -> None:
    ctx.enter_method(_ORIGIN)
    span = ctx.current_span_id()
    graft = _node(children=[_node(signature=MethodSignature("Smtp", "write", []))])

    ctx.emit_trace_node(graft, span)
    ctx.exit_method_with_return("done")

    (root,) = ctx.capture_trace().roots
    assert [c.signature.method_name for c in root.children] == ["send"]
    assert [g.signature.method_name for g in root.children[0].children] == ["write"]
    assert isinstance(root.outcome, Returned)


def test_a_null_outcome_is_legitimate_and_not_a_reason_to_drop(
    ctx: ContextVarNarrativeContext,
) -> None:
    """Synthetic launcher nodes carry no outcome."""
    ctx.enter_method(_ORIGIN)
    launcher = TraceNode(_GRAFTED, [], None)

    ctx.emit_trace_node(launcher, ctx.current_span_id())
    ctx.exit_method_with_return("done")

    (root,) = ctx.capture_trace().roots
    assert [c.signature.method_name for c in root.children] == ["send"]
