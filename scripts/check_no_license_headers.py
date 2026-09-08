# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""License-header absence gate (`poe check`, by design).

The inverse of the (private) publish pipeline's license gate: that pipeline stamps every tracked
source file with the BUSL-1.1 header **only in the published snapshot**, never in the private
tree (see its own comment: "exists ONLY in the published snapshot; nothing in the private tree
carries it"). Nothing enforced that convention on the private side, so a header pasted into a
source file in-tree by mistake would sit there, unnoticed and going stale, until publish time.

Scope is every git-tracked `*.py` file — a header *block* at the top of the file, not a string
mention anywhere in it: `packages/narrativetrace/tests/test_distribution_licensing.py` legitimately
asserts on `"BUSL-1.1"` and `"License-File: LICENSE"` deep in the file body, which is exactly why
only the first few lines are scanned.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEADER_SCAN_LINES = 10
HEADER_PATTERN = re.compile(
    r"SPDX-License-Identifier|Copyright \d{4} Empower Agile|"
    r"Licensed under the (Apache License|Business Source License)"
)


# Two environments need the non-git fallback below. (1) the (private) publish pipeline's
# --verify build runs this gate from a plain tar-extracted copy of the staged snapshot (git
# archive, then a disposable-directory copy) -- no .git anywhere in that pipeline. (2) ci.yml's
# container job: the workspace IS a git checkout, but it is owned by a different uid than the
# container user, so `git ls-files`
# refuses with "dubious ownership" and exits 128 -- which is why any git failure, not just a
# missing .git, must route here. The fallback is deliberately narrower than a bare rglob:
# by the time this gate runs,
# --verify has already run `uv sync --all-packages`, so a bare walk would also visit .venv's
# third-party packages and flag their own (legitimate) license headers as if they were this
# repo's. The recursive scope mirrors `poe bandit`'s own path list (packages examples scripts);
# conftest.py/conformance.py live directly at the repo root, so that one level is walked too.
_FALLBACK_SCOPE_DIRS = ("packages", "examples", "scripts")
_FALLBACK_EXCLUDE_DIRS = frozenset({".venv", "build", "dist", "__pycache__", "mutants", ".git"})


def _walk_python_files(repo_root: Path) -> list[Path]:
    """Fallback for a checkout with no `.git` (see the module comment above)."""
    files = [path.relative_to(repo_root) for path in repo_root.glob("*.py")]
    for scope in _FALLBACK_SCOPE_DIRS:
        scope_dir = repo_root / scope
        if not scope_dir.is_dir():
            continue
        for path in scope_dir.rglob("*.py"):
            relative = path.relative_to(repo_root)
            if _FALLBACK_EXCLUDE_DIRS & set(relative.parts):
                continue
            files.append(relative)
    return sorted(files)


def tracked_python_files(repo_root: Path) -> list[Path]:
    """Every git-tracked `*.py` file, as paths relative to `repo_root` -- or, wherever
    `git ls-files` cannot answer (no `.git` at all, git missing, or git refusing the
    repository, e.g. a container job's dubious-ownership rejection), every `*.py` file in
    this repo's own source scope (see `_walk_python_files`)."""
    if not (repo_root / ".git").exists():
        return _walk_python_files(repo_root)
    try:
        result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
            ["git", "ls-files", "--", "*.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return _walk_python_files(repo_root)
    if result.returncode != 0:
        return _walk_python_files(repo_root)
    return [Path(line) for line in result.stdout.splitlines() if line]


def carries_a_header_block(path: Path, repo_root: Path) -> bool:
    """True when `path`'s first `HEADER_SCAN_LINES` lines match `HEADER_PATTERN`."""
    lines = (repo_root / path).read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    return HEADER_PATTERN.search("\n".join(lines)) is not None


def find_offenders(repo_root: Path) -> list[Path]:
    """Files carrying a header block -- empty when NONE do (this repo's ordinary private-tree
    state) or when EVERY tracked file does (the (private) publish pipeline's --verify build runs
    `poe check`, this gate included, against its own already-stamped snapshot -- 100% coverage
    there is the correct, intended post-stamp state, not a finding). A MIX is what this gate
    actually exists to catch (see the module docstring): a header pasted into one file by
    mistake while its siblings carry none. Stamping is all-or-nothing by construction
    (the publish pipeline's header loop runs over every matching file, unconditionally), so a
    partial result outside those two tests is always exactly the drift this gate is for."""
    files = tracked_python_files(repo_root)
    stamped = [path for path in files if carries_a_header_block(path, repo_root)]
    if not stamped or len(stamped) == len(files):
        return []
    return stamped


def main() -> int:
    files = tracked_python_files(REPO_ROOT)
    offenders = find_offenders(REPO_ROOT)
    if offenders:
        print(
            "ERROR: license header block found in tracked source (stamped only at publish "
            "time by the (private) publish pipeline, never committed in-tree):"
        )
        for path in offenders:
            print(f"  {path}")
        return 1
    stamped = sum(1 for path in files if carries_a_header_block(path, REPO_ROOT))
    if files and stamped == len(files):
        print(
            f"OK: all {len(files)} tracked .py files carry a header block -- a stamped, "
            "publish-time snapshot (the publish pipeline's --verify build), not a finding."
        )
    else:
        print(f"OK: no license headers in {len(files)} tracked .py files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
