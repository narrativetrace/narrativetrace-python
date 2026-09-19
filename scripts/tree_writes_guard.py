# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Runs a command and fails if it left anything behind in the tracked working tree (`poe
check`'s pytest steps and the mutmut invocation `scripts/mutation_workers.py` drives are both
wrapped in this).

A test that asks a question must never answer it by performing the thing it is asking about --
"is a sync pending?" answered by actually syncing rewrites tracked pages under a test runner
nobody reviews the diff of. The `--check`/`--fix` (or `pending_sync`/`sync_repository`) pairs
already committed here split that way; this wrapper is what keeps the split honest for every
command a test suite runs, including one nobody has written the split for yet -- it costs one
`git status --porcelain` before and after the wrapped command and fails, naming every tracked
path that changed, rather than trusting each writer to have been reasoned through by hand.

Never skips: `git` failing to answer is a failure, not a pass. A guard that can silently no-op
is not a guard.
"""

from __future__ import annotations

import subprocess  # nosec B404 -- launches git/the wrapped command from a fixed or caller argv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def working_tree_status() -> list[str]:
    """`git status --porcelain` as lines, always read against `REPO_ROOT` regardless of the
    wrapped command's own working directory. Raises rather than skipping when git cannot
    answer."""
    result = subprocess.run(  # nosec B603, B607 -- fixed argv, no shell, no untrusted input
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"tree-writes-guard: git status exited {result.returncode}\n{result.stderr}"
        )
    return [line for line in result.stdout.split("\n") if line]


def new_working_tree_entries(before: list[str], after: list[str]) -> list[str]:
    """The `git status --porcelain` lines `after` has that `before` did not -- the working-tree
    changes the wrapped command is responsible for. Whole lines, so a path whose status changed
    (untracked becoming modified, say) still reads as new. Pure."""
    seen = set(before)
    return [line for line in after if line not in seen]


def report_lines(command: str, entries: list[str]) -> list[str]:
    """The failure report: what ran, what it wrote, and what to do about it."""
    return [
        f"tree-writes-guard: `{command}` changed {len(entries)} path(s) in the working tree:",
        *(f"  {line}" for line in entries),
        "A test must answer its question without writing where the repository lives. Make the",
        "'ask' half read-only, or take the output root as a parameter and point it at a temp dir.",
    ]


def run_guarded(argv: list[str]) -> int:
    """Runs `argv` (inheriting this process's own working directory, so a caller that needs the
    wrapped command to run from a particular directory -- mutmut needs its own package's `cwd`
    to find its `[tool.mutmut]` config -- still gets that), then fails if it left anything behind
    in the tracked tree. Returns the wrapped command's own exit code when the tree is unchanged.
    """
    if not argv:
        print("Usage: python scripts/tree_writes_guard.py <command> [args...]", file=sys.stderr)
        return 1
    before = working_tree_status()
    result = subprocess.run(argv, check=False)  # nosec B603 -- argv is the caller's own command
    after = working_tree_status()
    written = new_working_tree_entries(before, after)
    if written:
        for line in report_lines(" ".join(argv), written):
            print(line, file=sys.stderr)
        return 1
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    return run_guarded(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
