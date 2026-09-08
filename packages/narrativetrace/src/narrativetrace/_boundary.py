# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared exemption list for this runtime's best-effort exception boundaries.

The exemption Java's bug-hunt fix (``TraceBoundary``) draws around catching
``Throwable``: tracing's own machinery (a hostile context, listener, subscriber, or renderer) must
never poison a business call, but cancellation and interpreter-shutdown signals are not "just
another hostile collaborator" — they must still propagate immediately. Python's severe-condition
exceptions (``RecursionError``, ``MemoryError``) are already ``Exception`` subclasses, so the only
``BaseException``-but-not-``Exception`` types a plain ``except Exception`` misses are these four.
"""

from __future__ import annotations

import asyncio

PROPAGATED_EXCEPTIONS: tuple[type[BaseException], ...] = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    asyncio.CancelledError,
)
