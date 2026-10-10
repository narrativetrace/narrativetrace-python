# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The pytest row's wiring, as the framework table shows it: a test that requests the
``narrative_trace`` fixture and traces through it. Not collected here (the outer session disables
the plugin); ``test_fixture_wiring.py`` runs it under the real plugin. The doctor's
``config.pytest-fixture`` fix and ``llms-full.md`` carry the ``wiring`` region verbatim
(``narrativetrace_tooling/frameworks/wiring-snippets.md``)."""

from __future__ import annotations

# snippet:begin wiring
from narrativetrace import ContextVarNarrativeContext, trace_object


def test_place_order(narrative_trace: ContextVarNarrativeContext) -> None:
    service = trace_object(OrderService(), narrative_trace)

    assert service.place_order("cust-1", "prod-42") == "ORD-cust-1-prod-42"
    # snippet:end wiring


class OrderService:
    def place_order(self, customer_id: str, product_id: str) -> str:
        return f"ORD-{customer_id}-{product_id}"
