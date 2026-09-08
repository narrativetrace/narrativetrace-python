# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Characterization test: the FastAPI/ASGI demo exports a trace at the request boundary."""

from __future__ import annotations

from starlette.testclient import TestClient

from examples.fastapi_service.fastapi_service import CollectingExporter, build_app


def test_request_is_traced_and_exported() -> None:
    exporter = CollectingExporter()
    app = build_app(exporter)
    with TestClient(app) as client:
        response = client.get("/orders/cust-1")
    assert response.status_code == 200
    assert response.json() == {"result": "order for cust-1:prod-42"}
    assert len(exporter.calls) == 1
    tree, request_context = exporter.calls[0]
    assert not tree.is_empty
    assert request_context.status_code == 200


def test_service_span_carries_request_metadata() -> None:
    exporter = CollectingExporter()
    app = build_app(exporter)
    with TestClient(app) as client:
        client.get("/orders/cust-9")
    tree, _ = exporter.calls[0]
    root = tree.roots[0].span_context
    assert root is not None
    assert root.http_method == "GET"
    assert str(root.http_route) == "/orders/cust-9"
