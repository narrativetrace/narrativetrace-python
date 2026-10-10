# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The OpenTelemetry row's wiring fixture works as printed: a traced call through its context ends
as a finished span, and the narrative trace is still captured."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from opentelemetry import trace
from otel_harness import Harness

from narrativetrace import trace_object

_FIXTURE = Path(__file__).with_name("otel_wiring.py")


class OrderService:
    def place_order(self, customer_id: str) -> str:
        return f"ORD-{customer_id}"


def _load_fixture(otel: Harness, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Loads the fixture with ``trace.get_tracer`` answering the in-memory tracer — the global
    tracer provider can be set once per process, so a test never sets it."""
    monkeypatch.setattr(trace, "get_tracer", lambda *_args, **_kwargs: otel.tracer)
    spec = importlib.util.spec_from_file_location("otel_wiring_under_test", _FIXTURE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_traced_call_ends_as_a_span(otel: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    context = _load_fixture(otel, monkeypatch).context

    trace_object(OrderService(), context).place_order("cust-1")

    assert [span.name for span in otel.finished()] == ["OrderService.place_order"]


def test_the_narrative_trace_is_still_captured(
    otel: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _load_fixture(otel, monkeypatch).context

    trace_object(OrderService(), context).place_order("cust-1")

    assert [root.signature.method_name for root in context.capture_trace().roots] == ["place_order"]
