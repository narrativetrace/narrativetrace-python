# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The checkout's fraud check: one rule, so the scenario needs no risk engine."""

from __future__ import annotations


class RuleBasedFraudCheck:
    """An order at or above the review ceiling is refused."""

    REVIEW_CEILING_CENTS = 50_000
    """Orders at or above this total go to a human instead of to the gateway."""

    def approve(self, customer_id: str, amount_cents: int) -> bool:
        return amount_cents < self.REVIEW_CEILING_CENTS
