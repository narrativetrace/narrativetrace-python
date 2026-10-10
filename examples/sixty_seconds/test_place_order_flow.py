# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The smallest test that drives a real path through its collaborators, traced: the
``narrative_trace`` fixture is the capture, and every collaborator on the path is wrapped with it.
After a run, ``narrative-traces/structural/<module>/<test>.nt`` holds the flow's shape and
``narrative-traces/traces/<module>/<test>.md`` its values."""

from narrativetrace import ContextVarNarrativeContext, trace_object


class Inventory:
    def reserve(self, product_id: str, quantity: int) -> str:
        return f"R-{product_id}-{quantity}"


class OrderService:
    def __init__(self, inventory: Inventory) -> None:
        self._inventory = inventory

    def place_order(self, customer_id: str, product_id: str, quantity: int) -> str:
        reservation = self._inventory.reserve(product_id, quantity)
        return f"ORD-{customer_id}-{reservation}"


def test_customer_places_an_order(narrative_trace: ContextVarNarrativeContext) -> None:
    inventory = trace_object(Inventory(), narrative_trace)
    service = trace_object(OrderService(inventory), narrative_trace)

    assert service.place_order("cust-1", "prod-42", 3) == "ORD-cust-1-R-prod-42-3"
