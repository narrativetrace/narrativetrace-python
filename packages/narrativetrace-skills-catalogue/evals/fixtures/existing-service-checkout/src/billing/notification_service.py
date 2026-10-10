# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
class NotificationService:
    """Sends a short message to a customer."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, customer_id: str, message: str) -> None:
        self.sent.append((customer_id, message))
