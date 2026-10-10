# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from payments.gateway_client import GatewayClient


class PaymentService:
    def __init__(self, gateway: GatewayClient | None = None) -> None:
        self._gateway = gateway if gateway is not None else GatewayClient()

    def charge(self, customer_id: str, auth_token: str, amount: str) -> str:
        self._gateway.authorize("M-77", auth_token)
        return f"PAY-{customer_id}"
