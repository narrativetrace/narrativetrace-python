# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Applies a plan to a project directory. The only module in the installer that writes.

INTENT: keeps the decisions and the writing apart. The executor asks the project NOTHING — a plan
carries every file's whole text — so what a person reviewed as a diff is exactly what lands, and the
planners stay testable without a filesystem.

**@llmNote** Every write is temp-file-then-atomic-rename inside the TARGET directory, so a failed
write leaves the original file exactly as it was. A rename across filesystems, which a temp
directory elsewhere would force, is not atomic.

**@llmNote** Nothing here raises on a file that will not cooperate: the action is reported as
refused, the rest of the plan runs, and the exit code carries the news. A dry-run plan is the one
exception — applying one is a programming error, not a filesystem one.

**@sideEffects** Creates, replaces and deletes files under the given directory, and creates the
directories above them.
"""

from __future__ import annotations

import errno
import os
import tempfile
from pathlib import Path
from typing import Final

from narrativetrace_tooling.init.action import (
    Action,
    DeleteDirectory,
    DeleteFile,
    FileEdit,
    Refuse,
)
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.report import Applied, ExecutionReport, applied, refused

_TEMPORARY_PREFIX: Final = ".narrativetrace-"

_NOT_EMPTY: Final = frozenset({errno.ENOTEMPTY, errno.EEXIST})


def execute_plan(plan: InitPlan, project_directory: Path) -> ExecutionReport:
    """Applies every action, in order.

    :raises TypeError: when the plan or the directory is missing
    :raises ValueError: when the plan is a dry run, or the directory is not one
    """
    if plan is None or project_directory is None:
        raise TypeError("applying a plan needs the plan and a project directory")
    if plan.dry_run:
        raise ValueError("a dry run is shown, never applied")
    if not project_directory.is_dir():
        raise ValueError(f"{project_directory} is not a directory")
    results = [_apply(action, project_directory / action.path) for action in plan.actions]
    return ExecutionReport(plan.carrier, tuple(results))


def _apply(action: Action, target: Path) -> Applied:
    if isinstance(action, Refuse):
        return refused(action, action.reason)
    try:
        if isinstance(action, DeleteDirectory):
            return _delete_directory(action, target)
        return _apply_edit(action, target)
    except OSError as error:
        return refused(action, f"{type(error).__name__}: {error}")


def _apply_edit(action: FileEdit, target: Path) -> Applied:
    if isinstance(action, DeleteFile):
        target.unlink(missing_ok=True)
    else:
        _write(target, action.after)
    return applied(action)


def _delete_directory(action: DeleteDirectory, target: Path) -> Applied:
    """Removes a directory that is now empty; one that is not is reported, never emptied.

    **@llmNote** A path that is not a directory at all is reported too, rather than deleted: the
    planners only ever name a directory of ours here, so anything else means the project changed
    under the plan, and taking somebody's file with it would be the worst possible answer.
    """
    if not target.exists():
        return applied(action)
    try:
        target.rmdir()
    except OSError as error:
        if error.errno in _NOT_EMPTY:
            return refused(
                action, f"{target} is not empty — something else is in it, so it was left alone"
            )
        raise
    return applied(action)


def _write(target: Path, content: str) -> None:
    """Temp file beside the target, then an atomic rename over it."""
    directory = target.parent
    directory.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=directory, prefix=_TEMPORARY_PREFIX, suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
