# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared assertions every Tier A property test calls (the shared ``Oracles`` list).

Named here, once, so every property test in this package speaks the same oracle -- exactly the
role Java's own ``oracle/Oracles.java`` plays for its property tests.
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from collections.abc import Callable

BUDGET_SECONDS = 10.0
"""A hang detector, not a benchmark -- generous on purpose (mirrors Java's ``BUDGET_MILLIS``)."""

_TRACED_BUDGET_MULTIPLIER = 10
"""``poe check`` always runs this suite under ``pytest --cov``, whose branch tracer instruments
every line and branch executed -- measured ~9x wall-clock overhead on the worst-case (1 MiB)
corpus case alone. Scaling the budget when a trace function is active (``coverage.py`` or a
debugger) keeps the check a hang detector rather than a coverage-overhead detector; an actual
hang would still blow through even a 10x-scaled budget by orders of magnitude."""

MAX_OUTPUT_CHARS = 4 * 1024 * 1024
"""Mirrors Java's ``MAX_OUTPUT_BYTES``; this runtime measures characters, not encoded bytes."""


def sentinel_token() -> str:
    """A fresh, unique-per-call token a redaction oracle plants and then searches for."""
    return f"SENTINEL-{uuid.uuid4().hex}"


def within_budget[T](label: str, work: Callable[[], T]) -> T:
    """Runs ``work``, failing loudly if it takes longer than :data:`BUDGET_SECONDS` -- scaled by
    :data:`_TRACED_BUDGET_MULTIPLIER` while a trace function is active, since instrumentation
    overhead is not a hang."""
    budget = BUDGET_SECONDS * (_TRACED_BUDGET_MULTIPLIER if sys.gettrace() is not None else 1)
    start = time.perf_counter()
    result = work()
    elapsed = time.perf_counter() - start
    assert elapsed <= budget, f"{label} took {elapsed:.2f}s, budget is {budget}s"
    return result


def bounded_size(outputs: dict[str, str]) -> None:
    """Fails if any named output exceeds :data:`MAX_OUTPUT_CHARS`."""
    for name, text in outputs.items():
        assert len(text) <= MAX_OUTPUT_CHARS, f"{name} produced {len(text)} chars, unbounded"


def contains_nowhere(sentinel: str, outputs: dict[str, str]) -> None:
    """The redaction oracle: ``sentinel`` must appear in no output, whole or by prefix -- a
    partial leak through a truncating emitter is still a leak."""
    prefix = sentinel[:12]
    for name, text in outputs.items():
        assert sentinel not in text, f"{name} leaked the full sentinel"
        assert prefix not in text, f"{name} leaked a prefix of the sentinel"


def no_new_threads[T](work: Callable[[], T]) -> T:
    """The oracle that rendering starts no background thread that outlives the call."""
    before = {t.ident for t in threading.enumerate()}
    result = work()
    after = {t.ident for t in threading.enumerate()}
    assert after <= before, f"rendering left threads behind: {after - before}"
    return result


def idempotent(work: Callable[[], str]) -> str:
    """Rendering the same input twice must produce identical bytes."""
    first = work()
    second = work()
    assert first == second, "rendering the same input twice produced different output"
    return first
