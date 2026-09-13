# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared assertions every Tier A property test calls (the shared ``Oracles`` list).

Named here, once, so every property test in this package speaks the same oracle -- exactly the
role Java's own ``oracle/Oracles.java`` plays for its property tests.

Used to carry a sixth oracle, ``within_budget`` -- a wall-clock hang detector (``elapsed <=
BUDGET_SECONDS``, scaled 10x under `pytest --cov`'s tracer). Removed 2026-09-13 (family release
rule 3: wall-clock, GC and scheduler are never test inputs): it flaked on the corpus's
``long-1mib``/``huge-to-string`` worst cases under host load despite the scaling, because host
load -- not tracer overhead -- was what it was actually measuring. Each call site now asserts the
deterministic property the timing bound stood in for instead: a bounded-output test next to the
structural cap that makes the worst case cheap in the first place (see
``test_output_format_properties.py``'s and ``test_value_renderer_redaction_properties.py``'s
``TestBoundedWork``), or, where the property was genuinely about parse cost rather than output
size (``narrativetrace-asgi``'s 100,000-field ``traceparent`` header), a `pytest-benchmark` case
in the benchmark lane (`poe bench`/`poe bench-gate`), which is never part of the per-commit gate.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

MAX_OUTPUT_CHARS = 4 * 1024 * 1024
"""Mirrors Java's ``MAX_OUTPUT_BYTES``; this runtime measures characters, not encoded bytes."""


def sentinel_token() -> str:
    """A fresh, unique-per-call token a redaction oracle plants and then searches for."""
    return f"SENTINEL-{uuid.uuid4().hex}"


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
