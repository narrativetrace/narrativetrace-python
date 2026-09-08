# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the ASGI middleware's request-boundary capture, fail-safety, and isolation."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from narrativetrace_asgi import (
    NarrativeTraceMiddleware,
    RequestContext,
    UserContext,
    get_narrative_context,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from narrativetrace.context import (
    ContextSnapshot,
    ContextVarNarrativeContext,
    NarrativeContext,
)
from narrativetrace.context_export import MAX_LENGTH
from narrativetrace.ids import TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree


class RecordingExporter:
    """Captures every (tree, request_context) pair the middleware exports."""

    def __init__(self) -> None:
        self.calls: list[tuple[TraceTree, RequestContext]] = []

    def export(self, tree: TraceTree, request_context: RequestContext) -> None:
        self.calls.append((tree, request_context))


def _trace_a_call(sleep_ms: float = 0.0) -> None:
    """Records one enter/exit pair on the current request's context."""
    context = get_narrative_context()
    assert context is not None
    context.enter_method(MethodSignature("OrderService", "place", []))
    if sleep_ms:
        time.sleep(sleep_ms / 1000)
    context.exit_method_with_return('"ok"')


def _build_app(
    exporter: RecordingExporter | None = None,
    *,
    routes: list[Route] | None = None,
    context: NarrativeContext | None = None,
    **middleware_kwargs: object,
) -> tuple[NarrativeTraceMiddleware, NarrativeContext, RecordingExporter]:
    context = context or ContextVarNarrativeContext()
    exporter = exporter or RecordingExporter()

    async def handler(request: Request) -> JSONResponse:
        _trace_a_call(sleep_ms=2)
        return JSONResponse({"ok": True})

    app = Starlette(routes=routes or [Route("/orders", handler)])
    wrapped = NarrativeTraceMiddleware(app, context, exporter, **middleware_kwargs)  # type: ignore[arg-type]
    return wrapped, context, exporter


def _client(app: NarrativeTraceMiddleware) -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


class TestRequestBoundaryExport:
    def test_traced_request_exports_tree_with_status_and_duration(self) -> None:
        app, _, exporter = _build_app()
        with _client(app) as client:
            response = client.get("/orders")
        assert response.status_code == 200
        assert len(exporter.calls) == 1
        tree, rc = exporter.calls[0]
        assert not tree.is_empty
        assert rc.status_code == 200
        assert rc.duration_ms > 0

    def test_empty_tree_is_not_exported(self) -> None:
        async def bare(request: Request) -> PlainTextResponse:
            return PlainTextResponse("no trace")

        app, _, exporter = _build_app(routes=[Route("/bare", bare)])
        with _client(app) as client:
            assert client.get("/bare").status_code == 200
        assert exporter.calls == []

    def test_excluded_path_bypasses_tracing(self) -> None:
        async def health(request: Request) -> PlainTextResponse:
            assert get_narrative_context() is None
            return PlainTextResponse("ok")

        app, _, exporter = _build_app(routes=[Route("/health", health)], excluded_paths=["/health"])
        with _client(app) as client:
            assert client.get("/health").status_code == 200
        assert exporter.calls == []


async def _noop_app(scope: object, receive: object, send: object) -> None:
    pass


class TestLogScopeNormalization:
    """Adversarial-audit mirror (2026-09-02): a value read off the raw request (path, client
    IP, user identity) is control-stripped/length-capped before it reaches the log-scope keys, so
    it cannot forge a log line or blow past the cap -- matching the HTTP filter's own
    normalisation, as every runtime does for the same finding."""

    def _middleware(self) -> NarrativeTraceMiddleware:
        return NarrativeTraceMiddleware(_noop_app, ContextVarNarrativeContext())

    def test_a_newline_in_the_path_is_escaped_in_the_log_scope(self) -> None:
        scope = {"type": "http", "method": "GET", "path": "/orders\nFAKE LOG LINE", "headers": []}
        keys = self._middleware()._log_keys(scope, None)
        assert keys["httpRoute"] == "/orders\\nFAKE LOG LINE"

    def test_a_long_client_ip_is_capped_in_the_log_scope(self) -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/orders",
            "client": ("x" * 1000, 1),
            "headers": [],
        }
        keys = self._middleware()._log_keys(scope, None)
        assert len(keys["clientIp"]) == MAX_LENGTH + 1

    def test_a_newline_in_the_enduser_id_is_escaped(self) -> None:
        scope = {"type": "http", "method": "GET", "path": "/orders", "headers": []}
        keys = self._middleware()._log_keys(scope, UserContext(enduser_id="u1\nFAKE LOG LINE"))
        assert keys["enduserId"] == "u1\\nFAKE LOG LINE"

    def test_an_ordinary_path_is_unchanged(self) -> None:
        scope = {"type": "http", "method": "GET", "path": "/orders/42", "headers": []}
        keys = self._middleware()._log_keys(scope, None)
        assert keys["httpRoute"] == "/orders/42"


class TestFailSafety:
    def test_throwing_user_resolver_does_not_fail_request(self) -> None:
        def boom(scope: object) -> UserContext | None:
            raise RuntimeError("extractor boom")

        app, _, _ = _build_app(user_resolver=boom)
        with _client(app) as client:
            assert client.get("/orders").status_code == 200

    def test_throwing_exporter_does_not_fail_request(self) -> None:
        class Boom:
            def export(self, tree: TraceTree, request_context: RequestContext) -> None:
                raise RuntimeError("exporter boom")

        app, _, _ = _build_app(exporter=Boom())  # type: ignore[arg-type]
        with _client(app) as client:
            assert client.get("/orders").status_code == 200

    def test_handler_exception_propagates_and_exports_500(self) -> None:
        async def failing(request: Request) -> JSONResponse:
            _trace_a_call()
            raise ValueError("handler boom")

        app, _, exporter = _build_app(routes=[Route("/boom", failing)])
        with _client(app) as client, pytest.raises(ValueError, match="handler boom"):
            client.get("/boom")
        assert len(exporter.calls) == 1
        assert exporter.calls[0][1].status_code == 500


class _Boom(BaseException):
    """Deliberately not an ``Exception`` subclass — see ``narrativetrace._boundary``."""


class TestNoPoisonBaseExceptionBoundary:
    """Mirrors a Java bug-hunt finding (servlet/Micronaut filter totality) for this runtime's
    actual request boundary, the ASGI middleware. ``_prepare`` runs before
    the middleware's own ``try``/``finally`` even starts, so anything it does not catch blocks
    the ASGI app from running at all — a whole HTTP request failing because of tracing, the most
    severe shape of "poison" in this runtime.
    """

    def test_a_hostile_user_resolver_raising_baseexception_does_not_fail_the_request(self) -> None:
        def boom(scope: object) -> UserContext | None:
            raise _Boom("resolver broke with a non-Exception BaseException")

        app, _, _ = _build_app(user_resolver=boom)
        with _client(app) as client:
            assert client.get("/orders").status_code == 200

    def test_a_hostile_context_reset_raising_baseexception_does_not_block_the_app(self) -> None:
        class HostileContext(ContextVarNarrativeContext):
            def reset(self) -> None:
                raise _Boom("reset broke with a non-Exception BaseException")

        app, _, _ = _build_app(context=HostileContext())
        with _client(app) as client:
            assert client.get("/orders").status_code == 200

    def test_a_hostile_trace_id_raising_baseexception_does_not_block_the_app(self) -> None:
        class HostileContext(ContextVarNarrativeContext):
            def trace_id(self) -> TraceId:
                raise _Boom("trace_id broke with a non-Exception BaseException")

        app, _, _ = _build_app(context=HostileContext())
        with _client(app) as client:
            assert client.get("/orders").status_code == 200

    def test_a_hostile_exporter_raising_baseexception_does_not_fail_the_request(self) -> None:
        class HostileExporter:
            def export(self, tree: TraceTree, request_context: RequestContext) -> None:
                raise _Boom("exporter broke with a non-Exception BaseException")

        app, _, _ = _build_app(exporter=HostileExporter())  # type: ignore[arg-type]
        with _client(app) as client:
            assert client.get("/orders").status_code == 200

    def test_a_hostile_reset_at_cleanup_does_not_replace_the_business_exception(self) -> None:
        class HostileResetContext(ContextVarNarrativeContext):
            def reset(self) -> None:
                if self._resets == 0:  # allow the request-start reset; poison only cleanup
                    self._resets += 1
                    return
                raise _Boom("cleanup reset broke with a non-Exception BaseException")

            _resets = 0

        async def failing(request: Request) -> JSONResponse:
            _trace_a_call()
            raise ValueError("handler boom")

        app, _, _ = _build_app(routes=[Route("/boom", failing)], context=HostileResetContext())
        with _client(app) as client, pytest.raises(ValueError, match="handler boom"):
            client.get("/boom")


class TestTraceparent:
    def test_inbound_traceparent_is_adopted(self) -> None:
        app, _, exporter = _build_app()
        inbound = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        with _client(app) as client:
            client.get("/orders", headers={"traceparent": inbound})
        tree, _ = exporter.calls[0]
        root_sc = tree.roots[0].span_context
        assert root_sc is not None
        assert str(root_sc.trace_id) == "0af7651916cd43dd8448eb211c80319c"

    def test_traceparent_ignored_when_disabled(self) -> None:
        app, _, exporter = _build_app(adopt_traceparent=False)
        inbound = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        with _client(app) as client:
            client.get("/orders", headers={"traceparent": inbound})
        tree, _ = exporter.calls[0]
        root_sc = tree.roots[0].span_context
        assert root_sc is not None
        assert str(root_sc.trace_id) != "0af7651916cd43dd8448eb211c80319c"


class TestAccessor:
    def test_context_is_none_outside_request(self) -> None:
        assert get_narrative_context() is None

    def test_request_stamps_route_metadata(self) -> None:
        app, _, exporter = _build_app()
        with _client(app) as client:
            client.get("/orders")
        root_sc = exporter.calls[0][0].roots[0].span_context
        assert root_sc is not None
        assert root_sc.http_method == "GET"
        assert str(root_sc.http_route) == "/orders"


class TestUserContext:
    def test_user_resolver_stamps_identity_on_spans(self) -> None:
        def resolver(scope: object) -> UserContext:
            return UserContext(enduser_id="u-1", session_id="s-1", tenant_id="t-1")

        app, _, exporter = _build_app(user_resolver=resolver)
        with _client(app) as client:
            client.get("/orders")
        root_sc = exporter.calls[0][0].roots[0].span_context
        assert root_sc is not None
        assert str(root_sc.enduser_id) == "u-1"
        assert str(root_sc.session_id) == "s-1"
        assert str(root_sc.tenant_id) == "t-1"


class TestConcurrentIsolation:
    def test_concurrent_requests_do_not_cross_contaminate(self) -> None:
        exporter = RecordingExporter()
        context = ContextVarNarrativeContext()

        async def handler(request: Request) -> JSONResponse:
            ctx = get_narrative_context()
            assert ctx is not None
            ctx.enter_method(MethodSignature("Svc", request.path_params["name"], []))
            await asyncio.sleep(0.01)
            ctx.exit_method_with_return('"done"')
            return JSONResponse({"name": request.path_params["name"]})

        app = Starlette(routes=[Route("/svc/{name}", handler)])
        wrapped = NarrativeTraceMiddleware(app, context, exporter)

        async def drive() -> None:
            transport = httpx.ASGITransport(app=wrapped)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                names = [f"m{i}" for i in range(12)]
                await asyncio.gather(*(client.get(f"/svc/{n}") for n in names))

        asyncio.run(drive())

        assert len(exporter.calls) == 12
        for tree, _ in exporter.calls:
            assert len(tree.roots) == 1  # each request captured only its own single root


class TestAsyncWorkStartedByARequest:
    """The integration proof for snapshot adoption: a task a request launches is the request's.

    Java pins the same contract at `SpringIntegrationTest.asyncCallAppearsInTheCallersTrace`.
    """

    def _app(self) -> tuple[NarrativeTraceMiddleware, RecordingExporter]:
        exporter = RecordingExporter()
        context = ContextVarNarrativeContext()

        async def handler(request: Request) -> JSONResponse:
            ctx = get_narrative_context()
            assert ctx is not None
            span = ctx.enter_method(MethodSignature("OrderService", "placeOrder", []))
            snapshot = ctx.snapshot()
            ctx.exit_method_with_return('"ORD-1"', span_id=span)
            await asyncio.create_task(_notify_under(ctx, snapshot))
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/orders", handler)])
        return NarrativeTraceMiddleware(app, context, exporter), exporter

    def test_a_task_the_request_started_appears_in_the_requests_capture_exactly_once(self) -> None:
        wrapped, exporter = self._app()

        with _client(wrapped) as client:
            client.get("/orders")

        tree, _ = exporter.calls[0]
        names = _method_names(tree)
        assert names.count("notifyOrderPlaced") == 1
        assert names == ["placeOrder", "notifyOrderPlaced"]

    def test_the_task_carries_the_requests_trace_id(self) -> None:
        wrapped, exporter = self._app()

        with _client(wrapped) as client:
            client.get("/orders")

        tree, _ = exporter.calls[0]
        trace_ids = {
            str(n.span_context.trace_id) for n in _flatten(tree) if n.span_context is not None
        }
        assert len(trace_ids) == 1

    def test_two_requests_never_see_each_others_async_work(self) -> None:
        wrapped, exporter = self._app()

        with _client(wrapped) as client:
            client.get("/orders")
            client.get("/orders")

        assert len(exporter.calls) == 2
        for tree, _ in exporter.calls:
            assert _method_names(tree) == ["placeOrder", "notifyOrderPlaced"]


async def _notify_under(ctx: NarrativeContext, snapshot: ContextSnapshot) -> None:
    """The work a background task does, attached to the request that launched it."""
    with snapshot.activate():
        ctx.enter_method(MethodSignature("NotificationService", "notifyOrderPlaced", []))
        await asyncio.sleep(0)
        ctx.exit_method_with_return("true")


def _flatten(tree: TraceTree) -> list[TraceNode]:
    found: list[TraceNode] = []
    _collect(tree.roots, found)
    return found


def _collect(nodes: list[TraceNode], found: list[TraceNode]) -> None:
    for node in nodes:
        found.append(node)
        _collect(node.children, found)


def _method_names(tree: TraceTree) -> list[str]:
    return [n.signature.method_name for n in _flatten(tree)]
