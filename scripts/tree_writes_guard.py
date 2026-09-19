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

Never skips: git (or, with no `.git`, the fallback below) failing to answer is a failure, not a
pass. A guard that can silently no-op is not a guard.

The (private) publish pipeline's --verify build runs its checks (this one included) from a plain
`git archive` extraction of the staged snapshot -- no `.git` anywhere in that tree, so the git
mode above has nothing to ask. The fallback there is a content snapshot: path -> size, mtime and
a hash of every file in this repo's own tracked scope (the same non-git scope
`check_no_license_headers.py` already walks for the identical --verify shape, reused here rather
than re-declared), compared before and after the wrapped command exactly like the git mode
compares porcelain lines. Which mode ran is printed once, so a report is never ambiguous about
what it actually compared.
"""

from __future__ import annotations

import hashlib
import subprocess  # nosec B404 -- launches git/the wrapped command from a fixed or caller argv
import sys
from fnmatch import fnmatch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_MODE = "git"
CONTENT_SNAPSHOT_MODE = "content snapshot"

# `poe`'s tasks run this file directly (`python scripts/tree_writes_guard.py ...`), which puts
# this file's own directory, not the repo root, on `sys.path` -- the same reason every other
# script here that imports a sibling under `scripts.*` inserts the repo root first.
sys.path.insert(0, str(REPO_ROOT))

from scripts.check_no_license_headers import (  # noqa: E402
    _FALLBACK_EXCLUDE_DIRS,
    _FALLBACK_SCOPE_DIRS,
)


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


def guard_mode(repo_root: Path) -> tuple[str, str]:
    """`(GIT_MODE, "")` when `repo_root` is a git checkout `git status` can answer for, else
    `(CONTENT_SNAPSHOT_MODE, reason)` -- the fallback the (private) publish pipeline's `git
    archive` snapshot needs (see the module docstring), also reached by a checkout `git` itself
    refuses to read (a container checkout owned by another uid raises "dubious ownership") and by
    a missing `git` binary. `.git` existing on disk is not proof git can answer for it, so this
    asks git once (`git -C repo_root status --porcelain`) rather than only checking presence --
    rc 0 means git mode; anything else, including git not being installed at all, falls back,
    paired with the reason (git's first stderr line, or the missing-binary message) so the
    printed mode line `run_guarded` builds from it and the baseline it actually computes never
    disagree about why. Checked once by `run_guarded`."""
    try:
        result = subprocess.run(  # nosec B603, B607 -- fixed argv, no shell, no untrusted input
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return CONTENT_SNAPSHOT_MODE, f"git not found: {exc}"
    if result.returncode == 0:
        return GIT_MODE, ""
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    reason = stderr_lines[0] if stderr_lines else f"git status exited {result.returncode}"
    return CONTENT_SNAPSHOT_MODE, reason


def _gitignore_exclusions(repo_root: Path) -> tuple[frozenset[str], list[str]]:
    """This repo's own `.gitignore`, split into bare directory-name patterns (a trailing `/`,
    matched by component the same way `_FALLBACK_EXCLUDE_DIRS` already is) and bare file-name
    globs (matched against each file's basename) -- what an ordinary `poe check` run is expected
    to leave behind (test caches, coverage data, lint caches) that the content-snapshot baseline
    must not mistake for a tree write, since there is no git here to have already filtered it
    out. An anchored entry (a `/` before the trailing one) or a negation (`!...`) is not a shape
    this repo's own `.gitignore` uses today and is left unsupported rather than silently
    mishandled -- extend this the day `.gitignore` actually needs one."""
    dir_names: set[str] = set()
    file_globs: list[str] = []
    ignore_file = repo_root / ".gitignore"
    if not ignore_file.is_file():
        return frozenset(dir_names), file_globs
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        pattern = raw.strip()
        if not pattern or pattern.startswith("#") or pattern.startswith("!"):
            continue
        if pattern.endswith("/"):
            name = pattern[:-1]
            if "/" not in name:
                dir_names.add(name)
        elif "/" not in pattern:
            file_globs.append(pattern)
    return frozenset(dir_names), file_globs


def _scoped_files(repo_root: Path) -> list[Path]:
    """Every file the content-snapshot baseline covers: the same tracked scope
    `check_no_license_headers.py`'s own non-git fallback walks -- `packages`, `examples`,
    `scripts`, plus files directly at the repo root -- minus the same excluded directories, plus
    whatever this repo's own `.gitignore` additionally excludes (test caches, coverage data, lint
    caches an ordinary `poe check` run leaves behind -- see `_gitignore_exclusions`)."""
    ignored_dirs, ignored_file_globs = _gitignore_exclusions(repo_root)
    exclude_dirs = _FALLBACK_EXCLUDE_DIRS | ignored_dirs

    def _ignored_file(path: Path) -> bool:
        return any(fnmatch(path.name, glob) for glob in ignored_file_globs)

    files: list[Path] = []
    for entry in sorted(repo_root.iterdir()):
        if entry.is_file() and not _ignored_file(entry):
            files.append(entry.relative_to(repo_root))
    for scope in _FALLBACK_SCOPE_DIRS:
        scope_dir = repo_root / scope
        if not scope_dir.is_dir():
            continue
        for path in sorted(scope_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo_root)
            if exclude_dirs & set(relative.parts):
                continue
            if _ignored_file(path):
                continue
            files.append(relative)
    return files


def content_snapshot(repo_root: Path) -> dict[str, tuple[int, int, str]]:
    """The no-`.git` baseline: path (POSIX-slashed, relative to `repo_root`) -> (size, mtime_ns,
    sha256 hex) for every file `_scoped_files` names. Raises rather than returning a partial or
    empty baseline when the scope cannot be read -- read failures are a guard failure, not a
    silent "nothing to compare" (see the module docstring)."""
    if not repo_root.is_dir():
        raise RuntimeError(f"tree-writes-guard: repo root {repo_root} does not exist")
    snapshot: dict[str, tuple[int, int, str]] = {}
    for path in _scoped_files(repo_root):
        absolute = repo_root / path
        try:
            stat_result = absolute.stat()
            # nosec B324 -- a content fingerprint for change detection, not a security digest
            digest = hashlib.sha256(absolute.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError(
                f"tree-writes-guard: could not read {path} for the content-snapshot baseline: {exc}"
            ) from exc
        snapshot[path.as_posix()] = (stat_result.st_size, stat_result.st_mtime_ns, digest)
    return snapshot


def content_snapshot_diff(
    before: dict[str, tuple[int, int, str]], after: dict[str, tuple[int, int, str]]
) -> list[str]:
    """Content-snapshot counterpart of `new_working_tree_entries`, phrased in the same porcelain
    shorthand (`??` new, ` M` changed, ` D` removed) so a report from this mode names paths
    exactly the way the git mode does. Pure."""
    lines: list[str] = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            lines.append(f"?? {path}")
        elif path not in after:
            lines.append(f" D {path}")
        elif before[path] != after[path]:
            lines.append(f" M {path}")
    return lines


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
    mode, reason = guard_mode(REPO_ROOT)
    suffix = f" (git refused: {reason})" if mode == CONTENT_SNAPSHOT_MODE else ""
    print(f"tree-writes-guard: {mode}{suffix}", file=sys.stderr)
    if mode == GIT_MODE:
        before_git = working_tree_status()
    else:
        before_snapshot = content_snapshot(REPO_ROOT)
    result = subprocess.run(argv, check=False)  # nosec B603 -- argv is the caller's own command
    if mode == GIT_MODE:
        written = new_working_tree_entries(before_git, working_tree_status())
    else:
        written = content_snapshot_diff(before_snapshot, content_snapshot(REPO_ROOT))
    if written:
        for line in report_lines(" ".join(argv), written):
            print(line, file=sys.stderr)
        return 1
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    return run_guarded(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
