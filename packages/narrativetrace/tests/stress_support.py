# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared harness for the concurrency stress suite (see documentation/concurrency-stress.md).

Covers the same concurrency scenarios as the Java runtime's jcstress suite
(``narrativetrace-jcstress``), in this runtime's own idiom: the INVARIANTS are the cross-runtime
contract, not the tool. jcstress schedules interleavings by exhaustive JVM-level exploration;
CPython has no equivalent,
so every test here instead runs many repetitions of a barrier-synchronised race with the GIL's
switch interval lowered (more interleaving points per second) or, for asyncio, many repetitions
of a gather with randomised yield points inside each worker.

Two modes, selected by the ``NARRATIVETRACE_STRESS_LONG`` environment variable:

* unset (default) — a small, fixed-seed repetition count, wired into every ``poe check`` run.
  Finishes in seconds; a regression net for a race already found, not a search for a new one.
* ``"1"`` (``poe stress``) — a much larger, randomly-seeded repetition count for the scheduled
  sweep. The seed is included in every failure message so a crash a machine finds once is
  reproducible afterward.
"""

from __future__ import annotations

import contextlib
import os
import random
import sys
import threading
from collections.abc import Callable, Iterator

_LONG = os.environ.get("NARRATIVETRACE_STRESS_LONG") == "1"
_FIXED_SEED = 1337
_JOIN_TIMEOUT_SECONDS = 15.0


def stress_repeat(quick: int, long: int) -> int:
    """How many times a scenario repeats: ``quick`` by default, ``long`` under `poe stress`."""
    return long if _LONG else quick


def stress_seed() -> int:
    """A fresh seed for this run: fixed (reproducible) by default, random under `poe stress`."""
    return random.SystemRandom().randrange(2**32) if _LONG else _FIXED_SEED


@contextlib.contextmanager
def narrowed_switch_interval(interval: float = 1e-6) -> Iterator[None]:
    """Lowers the GIL's switch interval so threads interleave far more often than the 5ms default.

    A stress test's whole purpose is to hit a narrow timing window many times; CPython only
    preempts a thread between bytecode instructions when its switch interval elapses, so leaving
    it at the default makes most repetitions run one thread to completion before the next starts.
    """
    previous = sys.getswitchinterval()
    sys.setswitchinterval(interval)
    try:
        yield
    finally:
        sys.setswitchinterval(previous)


def run_barrier_synced(workers: list[Callable[[], None]]) -> None:
    """Starts every worker from one shared `threading.Barrier`, so each call hits the same
    contention window instead of a staggered thread-startup ramp diluting it.

    Propagates the first worker exception raised (after every thread has been joined), so a
    stress failure reports the actual assertion, not a hang.
    """
    barrier = threading.Barrier(len(workers))
    failures: list[BaseException] = []
    failures_lock = threading.Lock()

    def guarded(fn: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            barrier.wait(timeout=_JOIN_TIMEOUT_SECONDS)
            try:
                fn()
            except BaseException as exc:  # reported after every thread has joined, below
                with failures_lock:
                    failures.append(exc)

        return run

    threads = [threading.Thread(target=guarded(fn)) for fn in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
        if thread.is_alive():
            raise AssertionError("stress worker did not terminate within the join timeout")
    if failures:
        raise failures[0]
