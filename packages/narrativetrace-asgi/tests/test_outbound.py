# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins httpx outbound traceparent injection to the current request context."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from narrativetrace_asgi.accessor import _CURRENT_CONTEXT
from narrativetrace_asgi.outbound import (
    attach_traceparent,
    attach_traceparent_async,
    traceparent_header,
)
from narrativetrace_asgi.traceparent import parse_traceparent

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.ids import TraceId


def _request() -> httpx.Request:
    return httpx.Request("GET", "http://downstream/api")


class TestTraceparentHeader:
    def test_none_outside_request(self) -> None:
        assert traceparent_header() is None

    def test_uses_current_context_trace_id(self) -> None:
        context = ContextVarNarrativeContext()
        token = _CURRENT_CONTEXT.set(context)
        try:
            header = traceparent_header()
            assert header is not None
            parsed = parse_traceparent(header)
            assert parsed is not None
            assert parsed.trace_id == context.trace_id()
        finally:
            _CURRENT_CONTEXT.reset(token)


class TestAttach:
    def test_injects_header_when_context_present(self) -> None:
        context = ContextVarNarrativeContext()
        token = _CURRENT_CONTEXT.set(context)
        try:
            request = _request()
            attach_traceparent(request)
            assert "traceparent" in request.headers
            parsed = parse_traceparent(request.headers["traceparent"])
            assert parsed is not None
            assert parsed.trace_id == context.trace_id()
        finally:
            _CURRENT_CONTEXT.reset(token)

    def test_no_header_outside_request(self) -> None:
        request = _request()
        attach_traceparent(request)
        assert "traceparent" not in request.headers

    def test_does_not_overwrite_existing_header(self) -> None:
        context = ContextVarNarrativeContext()
        token = _CURRENT_CONTEXT.set(context)
        try:
            request = _request()
            request.headers["traceparent"] = "preset"
            attach_traceparent(request)
            assert request.headers["traceparent"] == "preset"
        finally:
            _CURRENT_CONTEXT.reset(token)

    def test_async_hook_injects_header(self) -> None:
        context = ContextVarNarrativeContext()
        token = _CURRENT_CONTEXT.set(context)
        try:
            request = _request()
            asyncio.run(attach_traceparent_async(request))
            assert "traceparent" in request.headers
        finally:
            _CURRENT_CONTEXT.reset(token)


class TestDocumentedEventHooksRecipe:
    """`documentation/guides/fastapi-asgi.md`'s "W3C traceparent" section, run through the real
    `httpx.Client`/`httpx.AsyncClient` `event_hooks` wiring the docs show — not `attach_traceparent`
    called directly on a hand-built request the way every test above this class does. This is the
    real path a server-to-server call actually takes."""

    @staticmethod
    def _mock_transport() -> tuple[httpx.MockTransport, dict[str, str]]:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(request.headers)
            return httpx.Response(200, json={"ok": True})

        return httpx.MockTransport(handler), captured

    def test_sync_client_event_hooks_matches_the_documented_recipe(self) -> None:
        context = ContextVarNarrativeContext()
        token = _CURRENT_CONTEXT.set(context)
        transport, captured = self._mock_transport()
        try:
            with httpx.Client(
                event_hooks={"request": [attach_traceparent]}, transport=transport
            ) as client:
                response = client.get("http://downstream/api")
        finally:
            _CURRENT_CONTEXT.reset(token)

        assert response.status_code == 200
        parsed = parse_traceparent(captured["traceparent"])
        assert parsed is not None
        assert parsed.trace_id == context.trace_id()

    def test_async_client_event_hooks_matches_the_documented_recipe(self) -> None:
        context = ContextVarNarrativeContext()
        transport, captured = self._mock_transport()

        # `ContextVarNarrativeContext` isolates asyncio tasks by design (see
        # documentation/choosing-an-integration.md's "Cross-thread / cross-task work" caveat):
        # `context.trace_id()` lazily generates a fresh id per contextvars scope, so the expected
        # id must be read from *inside* this same task, not from the outer sync scope afterward.
        async def make_request() -> tuple[httpx.Response, TraceId]:
            async with httpx.AsyncClient(
                event_hooks={"request": [attach_traceparent_async]}, transport=transport
            ) as client:
                response = await client.get("http://downstream/api")
            return response, context.trace_id()

        token = _CURRENT_CONTEXT.set(context)
        try:
            response, expected_trace_id = asyncio.run(make_request())
        finally:
            _CURRENT_CONTEXT.reset(token)

        assert response.status_code == 200
        parsed = parse_traceparent(captured["traceparent"])
        assert parsed is not None
        assert parsed.trace_id == expected_trace_id

    def test_attach_traceparent_async_is_required_for_an_async_client(self) -> None:
        """Pins the bug this module's docstring and the fastapi-asgi guide both used to show as
        the recommended recipe: `httpx.AsyncClient` `await`s every request hook, and the *sync*
        hook's `None` return cannot be awaited. Confirmed by running the previously-documented
        `httpx.AsyncClient(event_hooks={"request": [attach_traceparent]})` for real — this test
        pins that class of defect so the wrong pairing can never silently come back as "correct"."""
        context = ContextVarNarrativeContext()
        transport, _captured = self._mock_transport()

        async def make_request() -> httpx.Response:
            async with httpx.AsyncClient(
                event_hooks={"request": [attach_traceparent]}, transport=transport
            ) as client:
                return await client.get("http://downstream/api")

        token = _CURRENT_CONTEXT.set(context)
        try:
            with pytest.raises(TypeError, match="can't be used in 'await' expression"):
                asyncio.run(make_request())
        finally:
            _CURRENT_CONTEXT.reset(token)
