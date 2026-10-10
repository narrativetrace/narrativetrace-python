# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The structlog row's wiring fixture works as printed: once it has run, a structlog event logged
inside a request scope carries NarrativeTrace's correlation keys."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from narrativetrace.logging_bridge import _REQUEST_SCOPE, _SCOPE_STACK, request_log_scope

_FIXTURE = Path(__file__).with_name("structlog_wiring.py")


@pytest.fixture(autouse=True)
def _clean_slate() -> Iterator[None]:
    """No span or request scope left over from another test, and structlog's defaults after."""
    _SCOPE_STACK.set(None)
    _REQUEST_SCOPE.set(None)
    yield
    structlog.reset_defaults()


def _run_fixture() -> None:
    spec = importlib.util.spec_from_file_location("structlog_wiring_under_test", _FIXTURE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


def test_an_event_carries_the_correlation_keys(capsys: pytest.CaptureFixture[str]) -> None:
    _run_fixture()

    with request_log_scope({"httpMethod": "GET", "traceId": "req-1"}):
        structlog.get_logger().info("order placed")

    event = json.loads(capsys.readouterr().out)
    assert event == {"httpMethod": "GET", "traceId": "req-1", "event": "order placed"}
