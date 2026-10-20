# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The checkout's payment collaborator when the payment service is a different process."""

from __future__ import annotations

import httpx
from narrativetrace_asgi import attach_traceparent

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.services import PaymentService

_DECLINED_STATUS = 402


class HttpPaymentService(PaymentService):
    """Charges a card by POSTing to the payment service's ``endpoint``.

    The outbound half of cross-service correlation, in the shape any ``httpx`` client copies:
    ``attach_traceparent`` is a request hook that stamps the current request's trace id and calling
    span onto the call as a W3C ``traceparent`` header. The body is a comma-separated line rather
    than JSON on purpose -- this class exists to show the header, and a parser would be the only
    thing a reader had to skip.
    """

    def __init__(self, endpoint: str) -> None:
        super().__init__()
        self._endpoint = endpoint
        self._client = httpx.Client(event_hooks={"request": [attach_traceparent]})

    def charge(self, customer_id: str, amount_cents: int, card: str) -> str:
        response = self._client.post(
            self._endpoint, content=f"{customer_id},{amount_cents},{card}".encode()
        )
        if response.status_code == _DECLINED_STATUS:
            raise PaymentDeclinedError(response.text)
        return response.text

    def close(self) -> None:
        self._client.close()
