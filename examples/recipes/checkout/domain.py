# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The checkout's two plain data types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Order:
    """One placed order. A frozen dataclass, so a trace renders it field by field."""

    order_id: str
    customer_id: str
    sku: str
    quantity: int
    amount_cents: int


class PaymentDeclinedError(Exception):
    """The gateway refused the card. Says nothing about the stock that is still reserved."""
