# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
class PaymentGateway:
    """The card processor: authorize holds the amount, confirm captures it."""

    def __init__(self) -> None:
        self.captured: list[str] = []

    def authorize(self, amount: int, currency: str, card: str) -> str:
        if not card.startswith("card-"):
            raise ValueError("unknown card")
        return f"AUTH-{card}-{amount}-{currency}"

    def confirm(self, authorization: str) -> None:
        self.captured.append(authorization)
