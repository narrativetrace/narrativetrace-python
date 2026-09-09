# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Benchmark regression gate (`poe bench-gate`).

Runs the `test_bench_*.py` starter suite, autosaves the run under `.benchmarks/`, and fails if
any benchmark's mean time regressed against the most recently saved run on this machine — the
nightly's entry point on a fixed machine, never a per-commit/CI gate (host-baseline numbers are
not comparable across machines; the very first run has nothing to compare against and simply
passes while seeding one).

A plain Python wrapper rather than a `pyproject.toml` `cmd` string on purpose: pytest-benchmark's
percentage regression syntax needs a literal ``%`` (`mean:20%`), and radon's own config reader
(used by `poe metrics`) parses the whole `[tool]` table through a `ConfigParser` with
interpolation enabled — a bare ``%`` anywhere under `[tool.*]` in `pyproject.toml` breaks
`poe metrics` with "invalid interpolation syntax" (the same trap `[tool.poe.tasks.mutate-gate]`'s
own comment already documents for "80%"). Keeping the `%` inside a `.py` file instead of the TOML
file sidesteps it entirely.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REGRESSION_THRESHOLD = "mean:20%"
"""Fail the gate if a benchmark's mean time regressed by more than this against the last saved
run. 20% gives real machine-noise headroom (see the measured variance in a `poe bench` run)
while still catching a genuine regression, not just jitter."""


def main() -> int:
    result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        [
            sys.executable,
            "-m",
            "pytest",
            "--benchmark-only",
            "--benchmark-autosave",
            "--benchmark-compare",
            f"--benchmark-compare-fail={REGRESSION_THRESHOLD}",
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
