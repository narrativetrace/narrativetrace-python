# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
_RATES = {"EUR": 1.0, "CHF": 0.93, "GBP": 0.85}


class DailyRates:
    """Today's published rates: how much of a currency one euro buys."""

    def rate_for(self, currency: str) -> float:
        if currency not in _RATES:
            raise ValueError(f"no rate for {currency}")
        return _RATES[currency]
