# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A traced class whose annotations are live objects, not strings.

Deliberately WITHOUT ``from __future__ import annotations``: that import turns every annotation
into its source text, and the declared-type capture has to be exercised on both shapes. The rest of
the suite uses the future import, so this module covers the branch it hides.

Not ``conftest.py``: the workspace holds several, and pytest imports each under a rootdir-derived
name, so a shared basename would be ambiguous.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Receipt:
    """A domain return type, so the qualified-name rendering has something non-builtin to show."""

    total: int


class LiveLedger:
    """Annotated with real classes, so ``inspect.signature`` yields types rather than strings."""

    def post(self, customer_id: str, amount: int) -> Receipt:
        """Records a posting and returns its receipt."""
        return Receipt(amount)
