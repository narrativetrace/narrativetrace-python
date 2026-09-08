# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the trace_object wrapper: capture, templates, fast path, async, deferred exit."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from narrativetrace.context import NOOP_CONTEXT, ContextVarNarrativeContext
from narrativetrace.decorators import narrated, not_traced, on_error, traced
from narrativetrace.ids import SpanId
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel
from narrativetrace.markers import not_traced_field
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.rendering import ValueRenderer
from narrativetrace.signature import MethodSignature
from narrativetrace.trace_object import trace_object
from narrativetrace.values import RenderedValue


class BusinessError(Exception):
    pass


class Service:
    @property
    def name(self) -> str:
        return "svc"

    def add(self, a: int, b: int) -> int:
        return a + b

    @narrated("Greeting {who}")
    def greet(self, who: str) -> str:
        return f"hi {who}"

    @not_traced("password")
    def login(self, user: str, password: str) -> bool:
        return True

    @on_error(KeyError, "missing {key}")
    @on_error(BusinessError, "business failed for {key}")
    def lookup(self, key: str) -> str:
        raise BusinessError("boom")

    def blow_up(self) -> None:
        raise ValueError("kaboom")

    async def fetch(self, n: int) -> int:
        await asyncio.sleep(0)
        return n * 2

    async def fail_async(self) -> int:
        await asyncio.sleep(0)
        raise BusinessError("async boom")


@dataclass
class Card:
    number: str
    cvv: str = not_traced_field(default="")


@dataclass
class Basket:
    id: str
    card: Card


class PaymentService:
    @narrated("charging {card.cvv}")
    def charge(self, card: Card) -> bool:
        return True

    @narrated("charging {basket.card.cvv}")
    def checkout(self, basket: Basket) -> bool:
        return True


class AuthService:
    @narrated("login attempt for {user} with {password}")
    @not_traced("password")
    def login(self, user: str, password: str) -> bool:
        return True

    @on_error(ValueError, "login failed for {user} with {password}")
    @not_traced("password")
    def login_strict(self, user: str, password: str) -> bool:
        raise ValueError("nope")


@pytest.fixture
def ctx() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext()


class CountingRenderer(ValueRenderer):
    def __init__(self) -> None:
        super().__init__()
        self.render_calls = 0

    def render(self, value: object) -> str:
        self.render_calls += 1
        return super().render(value)


class TestBasicCapture:
    def test_method_return_captured(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)
        assert svc.add(2, 3) == 5
        node = ctx.capture_trace().roots[0]
        assert node.signature.class_name == "Service"
        assert node.signature.method_name == "add"
        assert isinstance(node.outcome, Returned)
        assert node.outcome.rendered_value == "5"

    def test_parameters_captured_by_name(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)
        svc.add(2, 3)
        params = ctx.capture_trace().roots[0].signature.parameters
        assert [(p.name, p.rendered_value) for p in params] == [("a", "2"), ("b", "3")]

    def test_class_name_override(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx, class_name="Orders")
        svc.add(1, 1)
        assert ctx.capture_trace().roots[0].signature.class_name == "Orders"

    def test_property_delegates_without_tracing(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)
        assert svc.name == "svc"
        assert ctx.capture_trace().is_empty

    def test_nested_wrapping(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(trace_object(Service(), ctx), ctx)
        assert svc.add(1, 2) == 3
        assert ctx.capture_trace().roots[0].signature.method_name == "add"


class TestTemplates:
    def test_narration_resolved(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)
        svc.greet("Alice")
        assert ctx.capture_trace().roots[0].signature.narration == "Greeting Alice"


class TestRedaction:
    def test_not_traced_param_is_redacted(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)
        svc.login("bob", "hunter2")
        params = {p.name: p for p in ctx.capture_trace().roots[0].signature.parameters}
        assert params["password"].rendered_value == "[REDACTED]"
        assert params["password"].redacted is True
        assert params["password"].structured_value is None
        assert params["user"].rendered_value == '"bob"'

    def test_secret_never_reaches_renderer(self, ctx: ContextVarNarrativeContext) -> None:
        renderer = CountingRenderer()
        svc = trace_object(Service(), ctx, renderer=renderer)

        class Boom:
            def __str__(self) -> str:  # pragma: no cover - must never be called
                raise AssertionError("secret was rendered")

        svc.login("bob", Boom())  # type: ignore[arg-type]
        assert ctx.capture_trace().roots[0].signature.parameters[1].rendered_value == "[REDACTED]"

    def test_a_template_naming_a_redacted_component_narrates_the_marker_not_the_value(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """Template-resolution family: naming a path never weakens the value's own
        rules, at any depth of the path."""
        svc = trace_object(PaymentService(), ctx)

        svc.charge(Card("4111", "123"))
        svc.checkout(Basket("b-1", Card("4111", "123")))

        roots = ctx.capture_trace().roots
        assert roots[0].signature.narration == "charging [REDACTED]"
        assert roots[1].signature.narration == "charging [REDACTED]"

    def test_a_narrated_simple_placeholder_naming_a_not_traced_parameter_narrates_the_marker(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """The redaction/template gap the other two `TestRedaction` cases don't cover between
        them: a decorator-marked `@not_traced` *parameter* (not a dataclass field) named by a
        *simple* `{password}` placeholder (not a `.property` path). `_build_capture` substitutes
        `REDACTED_MARKER` into the value map before either resolver call runs, so the resolver
        itself never sees the raw value for this form -- pinned end-to-end here."""
        svc = trace_object(AuthService(), ctx)
        svc.login("bob", "hunter2")
        narration = ctx.capture_trace().roots[0].signature.narration
        assert narration == "login attempt for bob with [REDACTED]"
        assert "hunter2" not in narration

    def test_an_on_error_simple_placeholder_naming_a_not_traced_parameter_narrates_the_marker(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """Same composition as above, through the `@on_error` call site (`resolve_error_context`)
        instead of `@narrated` -- both share `_build_capture`'s value map, but each resolver call
        site is worth pinning independently since a future change could thread them differently."""
        svc = trace_object(AuthService(), ctx)
        with pytest.raises(ValueError, match="nope"):
            svc.login_strict("bob", "hunter2")
        error_context = ctx.capture_trace().roots[0].signature.error_context
        assert error_context == "login failed for bob with [REDACTED]"
        assert "hunter2" not in (error_context or "")


class TestErrors:
    def test_exception_recorded_and_reraised(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)
        with pytest.raises(ValueError, match="kaboom"):
            svc.blow_up()
        assert isinstance(ctx.capture_trace().roots[0].outcome, Threw)

    def test_most_specific_on_error_resolved(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)
        with pytest.raises(BusinessError):
            svc.lookup("order-1")
        node = ctx.capture_trace().roots[0]
        assert node.signature.error_context == "business failed for order-1"


class Rogue:
    """A value whose rendering blows up — a lazy proxy over a closed session, say."""

    def __str__(self) -> str:
        raise ValueError("__str__ exploded")


class Wrapper:
    def __init__(self, value: object) -> None:
        self.value = value


class RogueService:
    @narrated("Processing {payload}")
    def process(self, payload: object) -> str:
        return "ok"

    @narrated("Processing {wrapper.value}")
    def process_property(self, wrapper: Wrapper) -> str:
        return "ok"

    @on_error(ValueError, "Failed while processing {payload}")
    def fail(self, payload: object) -> str:
        raise ValueError("the real failure")


class TestRogueStr:
    """A value whose ``__str__`` raises must not cost the span that narrates it.

    ``ValueRenderer`` has always treated a rogue ``__str__`` as a known hazard; the template
    path did not, and the proxy's own "capture setup must never crash the business call" guard
    turned that into a silently *untraced* call — the node vanished from the tree entirely.
    """

    def test_rogue_value_still_produces_a_span(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(RogueService(), ctx)
        assert svc.process(Rogue()) == "ok"
        assert ctx.capture_trace().roots[0].signature.method_name == "process"

    def test_narration_degrades_to_a_type_marker(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(RogueService(), ctx)
        svc.process(Rogue())
        assert ctx.capture_trace().roots[0].signature.narration == "Processing <Rogue>"

    def test_rogue_behind_a_property_placeholder_still_narrates(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        svc = trace_object(RogueService(), ctx)
        assert svc.process_property(Wrapper(Rogue())) == "ok"
        assert ctx.capture_trace().roots[0].signature.narration == "Processing <Rogue>"

    def test_on_error_template_does_not_mask_the_real_exception(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        svc = trace_object(RogueService(), ctx)
        with pytest.raises(ValueError, match="the real failure"):
            svc.fail(Rogue())

    def test_on_error_records_the_exit_it_used_to_drop(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        svc = trace_object(RogueService(), ctx)
        with pytest.raises(ValueError):
            svc.fail(Rogue())
        node = ctx.capture_trace().roots[0]
        assert isinstance(node.outcome, Threw)
        assert node.signature.error_context == "Failed while processing <Rogue>"


class TestFastPath:
    def test_off_context_does_zero_rendering(self) -> None:
        renderer = CountingRenderer()
        ctx = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.OFF))
        svc = trace_object(Service(), ctx, renderer=renderer)
        assert svc.add(1, 2) == 3
        assert renderer.render_calls == 0
        assert ctx.capture_trace().is_empty

    def test_noop_context_delegates(self) -> None:
        renderer = CountingRenderer()
        svc = trace_object(Service(), NOOP_CONTEXT, renderer=renderer)
        assert svc.add(4, 5) == 9
        assert renderer.render_calls == 0

    def test_narrative_level_suppresses_param_values(self) -> None:
        ctx = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.NARRATIVE))
        svc = trace_object(Service(), ctx)
        svc.add(1, 2)
        params = ctx.capture_trace().roots[0].signature.parameters
        assert all(p.rendered_value == "" for p in params)


class TestAsync:
    def test_async_method_traced(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)

        async def run() -> tuple[int, object]:
            result = await svc.fetch(21)
            return result, ctx.capture_trace()

        result, tree = asyncio.run(run())
        assert result == 42
        node = tree.roots[0]  # type: ignore[attr-defined]
        assert node.signature.method_name == "fetch"
        assert isinstance(node.outcome, Returned)
        assert node.outcome.rendered_value == "42"

    def test_async_exception_recorded_and_reraised(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)

        async def run() -> tuple[BaseException | None, object]:
            caught: BaseException | None = None
            try:
                await svc.fail_async()
            except BusinessError as exc:
                caught = exc
            return caught, ctx.capture_trace()

        caught, tree = asyncio.run(run())
        assert isinstance(caught, BusinessError)
        assert isinstance(tree.roots[0].outcome, Threw)  # type: ignore[attr-defined]


class ThrowingRenderer(ValueRenderer):
    def render(self, value: object) -> str:
        raise RuntimeError("renderer exploded")


class TestDeferredExitGuarantee:
    def test_sync_throwing_return_renderer_does_not_mask_result(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        svc = trace_object(Service(), ctx, renderer=ThrowingRenderer())
        assert svc.add(2, 3) == 5  # business result survives a broken renderer

    def test_async_throwing_return_renderer_does_not_mask_result(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        svc = trace_object(Service(), ctx, renderer=ThrowingRenderer())

        async def run() -> int:
            return await svc.fetch(21)

        assert asyncio.run(run()) == 42


class NoArgs:
    def ping(self) -> str:
        return "pong"


class Variadic:
    @traced("first", "second")
    def combine(self, *parts: str) -> str:
        return "-".join(parts)


class TestMoreCoverage:
    def test_return_renderer_failure_still_records_and_returns(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        # No params → capture setup succeeds; only the return renderer throws.
        svc = trace_object(NoArgs(), ctx, renderer=ThrowingRenderer())
        assert svc.ping() == "pong"
        node = ctx.capture_trace().roots[0]
        assert isinstance(node.outcome, Returned)
        assert node.outcome.rendered_value is None  # fallback exit

    def test_traced_names_for_varargs(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Variadic(), ctx)
        assert svc.combine("a", "b") == "a-b"
        params = ctx.capture_trace().roots[0].signature.parameters
        assert [p.name for p in params] == ["first", "second"]

    def test_wrong_arity_propagates_typeerror(self, ctx: ContextVarNarrativeContext) -> None:
        svc = trace_object(Service(), ctx)
        with pytest.raises(TypeError):
            svc.add(1)  # type: ignore[call-arg]
        assert isinstance(ctx.capture_trace().roots[0].outcome, Threw)


class TestProxyObjectMethodIdentity:
    """Mirrors a Java bug-hunt finding (proxy Object methods traced, equals not reflexive) for
    this runtime. ``_TracedProxy`` defines no ``__eq__``/``__hash__`` of its own,
    so Python resolves ``==``/``hash()``/set membership on ``type(proxy)`` — never through
    ``__getattr__`` — giving it ``object``'s identity-based semantics for free, exactly Java's
    fixed behavior (proxy identity, not delegated to the target). One divergence from Java's fix
    is deliberately NOT pinned or changed here: ``str()``/``repr()`` print the proxy's own type,
    not the target's, because ``object.__str__``/``__repr__`` are class-level defaults too and
    this runtime has no override delegating them — an existing, open design question
    ("Proxy identity... silently diverges from the wrapped object"),
    not something to resolve unilaterally here.
    """

    def test_a_proxy_equals_itself(self) -> None:
        svc = trace_object(Service(), ContextVarNarrativeContext())
        assert svc == svc  # noqa: PLR0124 - reflexivity is exactly what this test proves

    def test_two_proxies_over_the_same_target_are_not_equal(self) -> None:
        ctx = ContextVarNarrativeContext()
        target = Service()
        assert trace_object(target, ctx) != trace_object(target, ctx)

    def test_a_proxy_is_not_equal_to_its_target_or_to_none(self) -> None:
        target = Service()
        svc = trace_object(target, ContextVarNarrativeContext())
        assert svc != target
        assert svc != None  # noqa: E711 - deliberately exercising __eq__, not identity syntax

    def test_a_proxy_hashes_the_same_every_time(self) -> None:
        svc = trace_object(Service(), ContextVarNarrativeContext())
        assert hash(svc) == hash(svc)

    def test_a_proxy_behaves_in_a_set(self) -> None:
        ctx = ContextVarNarrativeContext()
        target = Service()
        svc = trace_object(target, ctx)
        assert {svc, svc, trace_object(target, ctx)}.__len__() == 2

    def test_object_methods_produce_no_trace_roots(self) -> None:
        ctx = ContextVarNarrativeContext()
        svc = trace_object(Service(), ctx)
        _ = (svc == svc, svc != Service(), hash(svc), str(svc), repr(svc))  # noqa: PLR0124
        assert ctx.capture_trace().is_empty

    def test_a_real_call_is_still_traced_beside_them(self) -> None:
        ctx = ContextVarNarrativeContext()
        svc = trace_object(Service(), ctx)
        _ = (svc == svc, hash(svc))  # noqa: PLR0124
        assert svc.add(2, 3) == 5
        assert len(ctx.capture_trace().roots) == 1


class _Signal(BaseException):
    """A hostile context's own failure — deliberately not an ``Exception`` subclass, mirroring
    Java's ``Throwable``/``Error`` split on Python's ``BaseException``/``Exception`` split.
    """


class _HostileEnterContext(ContextVarNarrativeContext):
    def enter_method(self, signature: MethodSignature) -> SpanId | None:
        raise _Signal("enter blew up")


class _HostileExitReturnContext(ContextVarNarrativeContext):
    def exit_method_with_return(
        self,
        rendered_return_value: str | None,
        structured_return_value: RenderedValue | None = None,
        span_id: SpanId | None = None,
    ) -> None:
        raise _Signal("exit-return blew up")


class _HostileExitExceptionContext(ContextVarNarrativeContext):
    def exit_method_with_exception(
        self,
        exception: BaseException,
        error_context: str | None = None,
        span_id: SpanId | None = None,
    ) -> None:
        raise _Signal("exit-exception blew up")


class _CancellingEnterContext(ContextVarNarrativeContext):
    def enter_method(self, signature: MethodSignature) -> SpanId | None:
        raise asyncio.CancelledError("cancelled during enter")


class TestNoPoisonProxyBoundary:
    """The proxy-totality / no-poison contract every runtime pins: the proxy's own dependencies —
    the context it reports to — must never be able to replace a business result or a business
    exception, and must never stop the business call from running. Unlike a hostile *value*
    (pinned in
    ``test_no_poison_contract.py``), these fixtures make the context/collaborator itself hostile,
    raising a ``BaseException`` that is not an ``Exception`` — a Java bug-hunt finding catches
    ``Throwable`` where its buggy code caught only ``Exception``; this is that same bug class
    applied to Python's exception hierarchy.
    """

    def test_a_hostile_enter_hook_still_runs_the_target_and_returns_its_value(self) -> None:
        svc = trace_object(Service(), _HostileEnterContext())
        assert svc.add(2, 3) == 5

    def test_a_hostile_exit_return_hook_does_not_replace_the_business_result(self) -> None:
        svc = trace_object(Service(), _HostileExitReturnContext())
        assert svc.add(2, 3) == 5

    def test_a_hostile_exit_exception_hook_does_not_replace_the_business_exception(self) -> None:
        svc = trace_object(Service(), _HostileExitExceptionContext())
        with pytest.raises(ValueError, match="kaboom"):
            svc.blow_up()

    def test_cancellation_during_enter_propagates_without_running_the_target_as_a_fallback(
        self,
    ) -> None:
        calls: list[tuple[int, int]] = []

        class _CountingService:
            def add(self, a: int, b: int) -> int:
                calls.append((a, b))
                return a + b

        svc = trace_object(_CountingService(), _CancellingEnterContext())
        with pytest.raises(asyncio.CancelledError):
            svc.add(1, 1)
        assert calls == []


class TestNoPoisonReturnRenderingAcrossLevels:
    """A bug-hunt finding: a hostile *return value* must reach the caller unpoisoned at every
    active tracing level, not only at ``DETAIL``. Already guaranteed by ``ValueRenderer``'s own
    totality (another bug-hunt finding) — this pins that guarantee from the proxy's perspective,
    across the level matrix, with no source change of its own (mirrors how Java's supplement
    closed the same finding as a regression pin on those earlier fixes).
    """

    class _HostileReturn:
        def __iter__(self) -> Any:  # pragma: no cover - never actually iterated
            raise AssertionError("must not be touched by tracing")

        def __str__(self) -> str:
            raise AssertionError("must not be touched by tracing")

    @pytest.mark.parametrize(
        "level",
        [TracingLevel.ERRORS, TracingLevel.SUMMARY, TracingLevel.NARRATIVE, TracingLevel.DETAIL],
    )
    def test_a_hostile_return_reaches_the_caller_at_every_active_level(
        self, level: TracingLevel
    ) -> None:
        ctx = ContextVarNarrativeContext(NarrativeTraceConfig(level))

        class Service2:
            def make(self) -> TestNoPoisonReturnRenderingAcrossLevels._HostileReturn:
                return TestNoPoisonReturnRenderingAcrossLevels._HostileReturn()

        svc = trace_object(Service2(), ctx)
        result = svc.make()
        assert isinstance(result, TestNoPoisonReturnRenderingAcrossLevels._HostileReturn)

    @pytest.mark.parametrize(
        "level",
        [TracingLevel.ERRORS, TracingLevel.SUMMARY, TracingLevel.NARRATIVE, TracingLevel.DETAIL],
    )
    def test_a_hostile_parameter_never_blocks_the_call_at_any_active_level(
        self, level: TracingLevel
    ) -> None:
        ctx = ContextVarNarrativeContext(NarrativeTraceConfig(level))

        class Service2:
            def accept(self, value: object) -> str:
                return "accepted"

        svc = trace_object(Service2(), ctx)
        assert svc.accept(self._HostileReturn()) == "accepted"
