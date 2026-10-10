# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from typing import Protocol


class CurrencyConverter(Protocol):
    def convert(self, euro_cents: int, currency: str) -> int:
        """``euro_cents`` in the minor unit (cents, rappen, pence) of ``currency``."""
        ...
