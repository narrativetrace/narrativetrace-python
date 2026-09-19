# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The worker-pool size every ``poe mutate*`` task runs mutmut with, and the launcher that
passes it as ``--max-children``.

2026-09-17 Linux nightly finding F3 (family-wide, mirrored in the TypeScript port's Stryker
``concurrency``): mutation runners size their worker pools from the HOST's core count. Inside a
cgroup-quota'd container that oversubscribes — three concurrent runs on one 8-core VM each
claimed all eight cores, and the runs then interfered with each other's timing-sensitive tests.

Order of precedence:

1. ``NT_MUTATION_WORKERS`` — an explicit positive integer from the caller (the Pro nightly passes
   ``NT_MUTATION_WORKERS=4``). A value that is set but not a positive integer is an error, never
   a silent fallback: a typo'd budget must not read as "use the whole host".
2. ``/sys/fs/cgroup/cpu.max`` — cgroup v2's ``"<quota> <period>"``, so ``"400000 100000"`` is a
   4-CPU quota → 4 workers (rounded UP, floored at 1, so a fractional quota still runs).
3. The runtime's CPU count — reached only when the quota reads ``max``, the file is absent (macOS,
   a bare host, cgroup v1), or its content does not parse. Never a bare host-core count on a
   quota'd host, which is the whole point of step 2.

``python scripts/mutation_workers.py [MUTANT_NAMES...]`` runs mutmut with the derived flag from
the caller's own working directory, so each ``poe mutate*`` task keeps its own ``cwd`` (and
therefore its own ``[tool.mutmut]`` config) — wrapped in ``scripts/tree_writes_guard.py``, so a
test that rewrites a tracked file under mutation fails the run instead of dirtying the tree
silently.
"""

from __future__ import annotations

import math
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.tree_writes_guard import run_guarded

CGROUP_CPU_MAX = Path("/sys/fs/cgroup/cpu.max")
WORKERS_ENV_VAR = "NT_MUTATION_WORKERS"


def _explicit_count(raw: str) -> int:
    try:
        count = int(raw)
    except ValueError:
        count = 0
    if count < 1:
        raise ValueError(f"{WORKERS_ENV_VAR} must be a positive integer, got {raw!r}")
    return count


def _quota_count(cgroup_cpu_max: str) -> int | None:
    """Workers from a cgroup v2 ``cpu.max`` line, or ``None`` when it sets no limit."""
    fields = cgroup_cpu_max.split()
    if len(fields) != 2 or fields[0] == "max":
        return None
    try:
        quota, period = int(fields[0]), int(fields[1])
    except ValueError:
        return None
    if quota < 1 or period < 1:
        return None
    return max(1, math.ceil(quota / period))


def worker_count(
    env: Mapping[str, str], cgroup_cpu_max: str | None, host_cpu_count: int | None
) -> int:
    """The number of mutation workers for this machine. Pure — every input is passed in."""
    explicit = env.get(WORKERS_ENV_VAR, "").strip()
    if explicit:
        return _explicit_count(explicit)
    from_quota = _quota_count(cgroup_cpu_max) if cgroup_cpu_max is not None else None
    if from_quota is not None:
        return from_quota
    return max(1, host_cpu_count or 1)


def _read_cgroup_cpu_max() -> str | None:
    try:
        return CGROUP_CPU_MAX.read_text(encoding="utf-8")
    except OSError:
        return None


def resolve_worker_count() -> int:
    """:func:`worker_count` against this process's real environment."""
    return worker_count(os.environ, _read_cgroup_cpu_max(), os.cpu_count())


def _source(env: Mapping[str, str], cgroup_cpu_max: str | None) -> str:
    if env.get(WORKERS_ENV_VAR, "").strip():
        return WORKERS_ENV_VAR
    if cgroup_cpu_max is not None and _quota_count(cgroup_cpu_max) is not None:
        return "cgroup cpu.max quota"
    return "runtime CPU count"


def mutmut_command(workers: int, extra_args: Sequence[str] = ()) -> list[str]:
    """The mutmut invocation for ``workers`` workers, plus any mutant-name arguments."""
    return [sys.executable, "-m", "mutmut", "run", "--max-children", str(workers), *extra_args]


def main(argv: Sequence[str] | None = None) -> int:
    extra_args = list(sys.argv[1:] if argv is None else argv)
    cgroup_cpu_max = _read_cgroup_cpu_max()
    workers = worker_count(os.environ, cgroup_cpu_max, os.cpu_count())
    print(
        f"mutation-workers: running mutmut with --max-children {workers} "
        f"(from {_source(os.environ, cgroup_cpu_max)})",
        flush=True,
    )
    return run_guarded(mutmut_command(workers, extra_args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
