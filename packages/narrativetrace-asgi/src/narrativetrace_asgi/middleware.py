# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pure-ASGI middleware capturing one narrative trace tree per HTTP request.

The request-filter behaviours (``NarrativeTraceFilter`` in the shared vocabulary): reset the
context, stamp request + user metadata, run the app, then capture and export the tree at the
request boundary with the real status code and duration. Observability never fails the request —
throwing extractors and exporters are swallowed, and the handler's own exception is always
re-raised un-masked (http-di report §TS-HTTP-1/2/3). Empty trees are not exported (§TS-HTTP-8),
excluded paths bypass tracing entirely (§TS-HTTP-6), and an inbound W3C ``traceparent`` is adopted
(§TS-HTTP-5).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable, MutableMapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from narrativetrace._boundary import PROPAGATED_EXCEPTIONS
from narrativetrace.context_export import export as context_export
from narrativetrace.logging_bridge import request_log_scope
from narrativetrace.metadata import ClientIp, EnduserId, HttpRoute, SessionId, TenantId
from narrativetrace_asgi.accessor import _CURRENT_CONTEXT
from narrativetrace_asgi.traceparent import parse_traceparent

if TYPE_CHECKING:
    from narrativetrace.context import NarrativeContext
    from narrativetrace.tree import TraceTree

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_DEFAULT_ERROR_STATUS = 500
_DEFAULT_OK_STATUS = 200


@dataclass(frozen=True, slots=True)
class RequestContext:
    """The HTTP outcome handed to an exporter at request completion."""

    status_code: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class UserContext:
    """Optional end-user/session/tenant identity resolved from a request."""

    enduser_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None


class RequestExporter(Protocol):
    """Sink receiving the captured tree plus HTTP outcome at the request boundary."""

    def export(self, tree: TraceTree, request_context: RequestContext) -> None: ...


class RequestUserResolver(Protocol):
    """Resolves end-user identity from an ASGI scope (may return ``None``)."""

    def __call__(self, scope: Scope) -> UserContext | None: ...


class NarrativeTraceMiddleware:
    """Wraps an ASGI app so each HTTP request is captured as one narrative trace."""

    def __init__(
        self,
        app: ASGIApp,
        context: NarrativeContext,
        exporter: RequestExporter | None = None,
        *,
        user_resolver: RequestUserResolver | None = None,
        excluded_paths: Iterable[str] = (),
        adopt_traceparent: bool = True,
    ) -> None:
        self._app = app
        self._context = context
        self._exporter = exporter
        self._user_resolver = user_resolver
        self._excluded_paths = frozenset(excluded_paths)
        self._adopt_traceparent = adopt_traceparent

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "") in self._excluded_paths:
            await self._app(scope, receive, send)
            return
        user = self._prepare(scope)
        status = {"code": None}
        error = False
        start = time.monotonic()
        token = _CURRENT_CONTEXT.set(self._context)
        try:
            with request_log_scope(self._log_keys(scope, user)):
                await self._app(scope, receive, self._wrap_send(send, status))
        except BaseException:
            error = True
            raise
        finally:
            self._finish(status["code"], start, error=error)
            _CURRENT_CONTEXT.reset(token)

    @staticmethod
    def _wrap_send(send: Send, status: MutableMapping[str, Any]) -> Send:
        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        return wrapped

    def _prepare(self, scope: Scope) -> UserContext | None:
        """Fail-safe: reset, adopt traceparent, and stamp request + user metadata.

        Called before the request-handling ``try``/``finally`` even starts, so a failure here
        that this guard did not catch would block the ASGI app from running at all — this is the
        request-boundary mirror of a bug-hunt finding, hence ``BaseException`` rather than
        ``Exception`` (see ``narrativetrace._boundary``).
        """
        try:
            self._context.reset()
            self._adopt(scope)
            self._stamp_request(scope)
            user = self._resolve_user(scope)
            self._stamp_user(user)
            return user
        except PROPAGATED_EXCEPTIONS:
            raise
        except BaseException:
            return None

    def _adopt(self, scope: Scope) -> None:
        if not self._adopt_traceparent:
            return
        parsed = parse_traceparent(_header(scope, b"traceparent"))
        if parsed is not None:
            self._context.adopt_trace_id(parsed.trace_id)

    def _stamp_request(self, scope: Scope) -> None:
        route = HttpRoute.of(scope["path"]) if scope.get("path") else None
        client = scope.get("client")
        client_ip = ClientIp.of(client[0]) if client else None
        self._context.set_request_context(scope.get("method"), route, client_ip)

    def _resolve_user(self, scope: Scope) -> UserContext | None:
        if self._user_resolver is None:
            return None
        return self._user_resolver(scope)

    def _stamp_user(self, user: UserContext | None) -> None:
        if user is None:
            return
        self._context.set_user_context(
            EnduserId.of(user.enduser_id) if user.enduser_id else None,
            SessionId.of(user.session_id) if user.session_id else None,
            TenantId.of(user.tenant_id) if user.tenant_id else None,
        )

    def _log_keys(self, scope: Scope, user: UserContext | None) -> dict[str, str]:
        keys: dict[str, str] = {}
        method = scope.get("method")
        if method:
            keys["httpMethod"] = context_export(method)
        if scope.get("path"):
            keys["httpRoute"] = context_export(scope["path"])
        client = scope.get("client")
        if client:
            keys["clientIp"] = context_export(client[0])
        self._add_trace_keys(keys)
        _add_user_keys(keys, user)
        return keys

    def _add_trace_keys(self, keys: dict[str, str]) -> None:
        """Evaluated before the app runs (it feeds the ``with request_log_scope(...)`` call), so
        this must not block the request either — same ``BaseException`` reasoning as ``_prepare``.
        """
        try:
            trace_id = self._context.trace_id()
        except PROPAGATED_EXCEPTIONS:
            raise
        except BaseException:
            return
        keys["traceId"] = str(trace_id)
        keys["traceName"] = trace_id.human_name()

    def _finish(self, status_code: int | None, start: float, *, error: bool) -> None:
        """Runs in the request's ``finally``: capture/export must never replace the request's
        real outcome (a bug-hunt finding's "cleanup cannot decide the request's outcome").
        """
        try:
            tree = self._context.capture_trace()
            if not tree.is_empty and self._exporter is not None:
                duration_ms = int((time.monotonic() - start) * 1000)
                code = _resolve_status(status_code, error=error)
                self._exporter.export(tree, RequestContext(code, duration_ms))
        except PROPAGATED_EXCEPTIONS:
            raise
        except BaseException:
            pass
        finally:
            _safe_reset(self._context)


def _resolve_status(status_code: int | None, *, error: bool) -> int:
    if status_code is not None:
        return status_code
    return _DEFAULT_ERROR_STATUS if error else _DEFAULT_OK_STATUS


def _add_user_keys(keys: dict[str, str], user: UserContext | None) -> None:
    if user is None:
        return
    if user.enduser_id:
        keys["enduserId"] = context_export(user.enduser_id)
    if user.session_id:
        keys["sessionId"] = context_export(user.session_id)
    if user.tenant_id:
        keys["tenantId"] = context_export(user.tenant_id)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return None


def _safe_reset(context: NarrativeContext) -> None:
    try:
        context.reset()
    except PROPAGATED_EXCEPTIONS:
        raise
    except BaseException:
        pass
