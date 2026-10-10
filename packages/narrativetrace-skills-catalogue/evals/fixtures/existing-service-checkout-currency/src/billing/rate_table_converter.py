# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from billing.daily_rates import DailyRates


class RateTableConverter:
    """Converts at the rate ``DailyRates`` publishes, keeping the amount exact until the last
    step."""

    def __init__(self, rates: DailyRates) -> None:
        self._rates = rates

    def convert(self, euro_cents: int, currency: str) -> int:
        rate = self._rates.rate_for(currency)
        if currency == "EUR":
            return euro_cents
        whole_units = round(euro_cents / 100 * rate)
        return whole_units * 100
