# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
class GatewayClient:
    def authorize(self, merchant_id: str, gateway_ref: str) -> str:
        return "AUTH-OK"
