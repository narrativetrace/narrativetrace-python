# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins httpx outbound traceparent injection to the current request context."""

from __future__ import annotations

import asyncio

import httpx
from narrativetrace_asgi.accessor import _CURRENT_CONTEXT
from narrativetrace_asgi.outbound import (
    attach_traceparent,
    attach_traceparent_async,
    traceparent_header,
)
from narrativetrace_asgi.traceparent import parse_traceparent

from narrativetrace.context import ContextVarNarrativeContext


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
