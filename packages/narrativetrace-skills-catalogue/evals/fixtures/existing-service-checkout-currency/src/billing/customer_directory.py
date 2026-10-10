# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
class CustomerDirectory:
    """What we know about a customer's card."""

    def __init__(self, card_currencies: dict[str, str]) -> None:
        self._card_currencies = card_currencies

    def card_currency(self, customer_id: str) -> str:
        return self._card_currencies.get(customer_id, "EUR")
