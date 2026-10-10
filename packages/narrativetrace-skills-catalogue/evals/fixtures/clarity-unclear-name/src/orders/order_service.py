# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Places and prices customer orders. It works; its names say little about what it does."""


class OrderService:
    def proc(self, d, x):
        return f"ORD-{d}-{x}"

    def calc(self, val, tmp):
        return val * tmp


class InvoiceFormatter:
    def fmt(self, o):
        return f"Invoice for {o}"
