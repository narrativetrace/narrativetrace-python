# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Signs a customer in before the checkout charges them."""

from __future__ import annotations


class CustomerAccounts:
    """In-memory accounts. The parameter is named ``password`` -- that name is the whole point of
    documentation/recipes/keep-secrets-out-of-the-logs.md."""

    def sign_in(self, customer_id: str, password: str) -> str:
        """Returns the session id the checkout carries for the rest of the request.

        Raises ``ValueError`` when the password is blank.
        """
        if not password.strip():
            raise ValueError("password must not be blank")
        return f"SESSION-{customer_id}"
