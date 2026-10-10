# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""shopkit -- a checkout flow with hooks.

``CheckoutFlow.run`` takes a payment through a gateway and fires the flow's hooks:
``payment_succeeded`` once the payment has gone through, and ``checkout_completed`` at the end.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = ["CheckoutFlow", "Hooks"]


class Hooks:
    """Named hooks; a handler registered with ``on`` is called with the hook's arguments."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = {}

    def on(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(handler: Callable[..., Any]) -> Callable[..., Any]:
            self._handlers.setdefault(name, []).append(handler)
            return handler

        return register

    def fire(self, name: str, *args: Any) -> None:
        for handler in self._handlers.get(name, []):
            handler(*args)


class CheckoutFlow:
    """One payment: authorize, then capture."""

    def __init__(self, gateway: Any, hooks: Hooks) -> None:
        self._gateway = gateway
        self._hooks = hooks

    def run(self, invoice: Any, card: str) -> str:
        authorization = self._gateway.authorize(invoice.amount_cents, card)
        self._hooks.fire("payment_succeeded", invoice)
        self._gateway.confirm(authorization)
        self._hooks.fire("checkout_completed", invoice)
        return authorization
