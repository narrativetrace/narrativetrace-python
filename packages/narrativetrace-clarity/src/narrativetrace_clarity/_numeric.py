# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared 2-dp formatting matching Java's ``String.format("%.2f")`` (HALF_UP rounding)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def two_dp(score: float) -> str:
    """Formats a score to two decimal places using HALF_UP rounding."""
    return str(Decimal(score).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
