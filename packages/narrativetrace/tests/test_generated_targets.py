# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""List 1 of the instrumentation exclusions: targets and members that are structurally never a
business boundary in Python -- C-accelerated builtins, ``functools.partial`` objects, and members
whose name no ``def`` statement can produce -- are never traced, and no configuration switches that
back on."""

from __future__ import annotations

import functools
from collections.abc import Callable

import pytest

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.trace_object import trace_object


@pytest.fixture
def ctx() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext()


def _add(a: int, b: int) -> int:
    return a + b


class Ledger:
    """A business class living in this (included) module."""

    def __init__(self) -> None:
        self.bound_builtin = list[int]().append
        self.builtin_function = len
        self.partial_member = functools.partial(_add, 1)
        self.anonymous: Callable[[int], int] = lambda x: x * 2

    def post(self, amount: int) -> int:
        return amount

    def _internal(self, amount: int) -> int:
        return amount

    @functools.cache  # noqa: B019 - a cached business method, deliberately
    def cached_post(self, amount: int) -> int:
        return amount


class UserList(list[int]):
    """A user's own subclass of a builtin: a business class, not a builtin."""

    def total(self) -> int:
        return sum(self)


class TestTargetsThatAreNeverTraced:
    @pytest.mark.parametrize(
        "target",
        [[1, 2], {"a": 1}, "text", 42, (1, 2), {1}],
        ids=["list", "dict", "str", "int", "tuple", "set"],
    )
    def test_a_builtin_typed_target_is_returned_unwrapped(
        self, ctx: ContextVarNarrativeContext, target: object
    ) -> None:
        assert trace_object(target, ctx) is target

    def test_a_functools_partial_target_is_returned_unwrapped(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        target = functools.partial(_add, 1)
        assert trace_object(target, ctx) is target

    def test_a_functools_partialmethod_target_is_returned_unwrapped(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        target = functools.partialmethod(_add, 1)
        assert trace_object(target, ctx) is target


class TestMembersThatAreNeverTraced:
    @pytest.mark.parametrize("member", ["bound_builtin", "builtin_function"])
    def test_a_c_accelerated_callable_member_runs_untraced(
        self, ctx: ContextVarNarrativeContext, member: str
    ) -> None:
        ledger = trace_object(Ledger(), ctx)
        getattr(ledger, member)([5] if member == "builtin_function" else 5)
        assert ctx.capture_trace().is_empty

    def test_a_functools_partial_member_runs_untraced(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ledger = trace_object(Ledger(), ctx)
        assert ledger.partial_member(2) == 3
        assert ctx.capture_trace().is_empty

    def test_a_lambda_member_runs_untraced(self, ctx: ContextVarNarrativeContext) -> None:
        ledger = trace_object(Ledger(), ctx)
        assert ledger.anonymous(4) == 8
        assert ctx.capture_trace().is_empty

    def test_a_private_member_runs_untraced(self, ctx: ContextVarNarrativeContext) -> None:
        ledger = trace_object(Ledger(), ctx)
        assert ledger._internal(3) == 3
        assert ctx.capture_trace().is_empty


class TestNearMissesStillTraced:
    def test_an_ordinary_business_method_is_traced(self, ctx: ContextVarNarrativeContext) -> None:
        trace_object(Ledger(), ctx).post(7)
        assert [n.signature.method_name for n in ctx.capture_trace().roots] == ["post"]

    def test_a_user_subclass_of_a_builtin_is_traced(self, ctx: ContextVarNarrativeContext) -> None:
        assert trace_object(UserList([1, 2]), ctx).total() == 3
        assert [n.signature.method_name for n in ctx.capture_trace().roots] == ["total"]

    def test_an_lru_cached_business_method_is_traced(self, ctx: ContextVarNarrativeContext) -> None:
        trace_object(Ledger(), ctx).cached_post(9)
        assert [n.signature.method_name for n in ctx.capture_trace().roots] == ["cached_post"]
