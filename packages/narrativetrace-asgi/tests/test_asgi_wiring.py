# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ASGI row's wiring fixture works as printed: one request through the app prints a trace of
that request, and only that request."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

_FIXTURE = Path(__file__).with_name("asgi_wiring.py")


def _load_fixture() -> ModuleType:
    spec = importlib.util.spec_from_file_location("asgi_wiring_under_test", _FIXTURE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_request_prints_its_own_trace(capsys: pytest.CaptureFixture[str]) -> None:
    wiring = _load_fixture()

    response = TestClient(wiring.app).get("/orders/cust-1")

    assert response.json() == {"order": "ORD-cust-1-prod-42"}
    printed = capsys.readouterr().out
    assert 'OrderService.place_order(customer_id: "cust-1", product_id: "prod-42")' in printed


def test_each_request_prints_only_its_own_calls(capsys: pytest.CaptureFixture[str]) -> None:
    client = TestClient(_load_fixture().app)

    client.get("/orders/first")
    capsys.readouterr()
    client.get("/orders/second")

    printed = capsys.readouterr().out
    assert '"second"' in printed
    assert '"first"' not in printed


class _RecordingStdout(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flushed_at: list[int] = []

    def flush(self) -> None:
        self.flushed_at.append(len(self.getvalue()))
        super().flush()


def test_each_trace_is_flushed_as_it_is_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A server's stdout is a pipe in production (a container, a process manager, a test harness)
    and block-buffered there: an unflushed trace waits for kilobytes more output, or for an exit
    that may never flush it. The printed wiring must reach the reader with each request."""
    stdout = _RecordingStdout()
    monkeypatch.setattr(sys, "stdout", stdout)

    TestClient(_load_fixture().app).get("/orders/cust-1")

    assert "OrderService.place_order" in stdout.getvalue()
    assert stdout.flushed_at[-1:] == [len(stdout.getvalue())]
