# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A real temporary project for a property to run in, and the readings a property takes of one.

The generative properties need a filesystem — "apply" means nothing without one — and they need a
clean one per example, so this owns the create-run-delete shape and the two whole-tree readings both
property modules compare against: every file with its exact bytes, and every symbolic link left
behind.

**@llmNote** The walk never DESCENDS through a link (``Path.rglob``'s own behaviour for ``**``), and
the clean-up unlinks a link rather than recursing into it (:func:`shutil.rmtree` tests each entry
with ``follow_symlinks=False``), so a project holding a link to a tree outside the temp directory
never costs that tree a file. A link to a FILE is a different matter: ``is_file`` and ``read_bytes``
follow one, so :func:`snapshot_of` reports the target's bytes under the link's own path. That is
deliberate — a property asserting no page was written through a link wants to see what the link
resolves to — and it is why :func:`links_under` exists separately: it is the only reading here that
tells a link from a real file.

Mirrors the Java port's ``Projects`` test helper.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def in_a_temporary_one(prefix: str) -> Iterator[Path]:
    """Yields a fresh temp project, and deletes it whatever happened."""
    project = Path(tempfile.mkdtemp(prefix=f"{prefix}-"))
    try:
        yield project
    finally:
        shutil.rmtree(project, ignore_errors=True)


def snapshot_of(project: Path) -> dict[str, str]:
    """Every file under the project, by relative path, with its exact bytes."""
    return {
        file.relative_to(project).as_posix(): file.read_bytes().decode("utf-8")
        for file in sorted(project.rglob("*"))
        if file.is_file()
    }


def links_under(project: Path) -> list[str]:
    """Every symbolic link left anywhere under the project, by relative path."""
    return sorted(
        path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_symlink()
    )
