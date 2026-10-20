# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The quality gate's ruff steps run uncached.

Ruff's cache is keyed by a file's path and metadata (size, timestamp), not its content. Reordering
two import lines keeps the size, and a rewrite inside a bind mount's timestamp granularity leaves
the stale entry valid: on 2026-10-20 a committed import-order violation passed ``poe check`` in the
container and failed the host publish rehearsal's fresh install (``ruff check`` passed, ``ruff check
--no-cache`` found it). A gate never depends on a cache, so ``check``'s ruff steps carry
``--no-cache``; the interactive ``lint`` task may keep it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "packages").is_dir():
            return candidate
    raise RuntimeError(f"no workspace root (pyproject.toml + packages/) above {__file__}")


def _tasks() -> dict[str, Any]:
    with (_find_repo_root() / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    tasks: dict[str, Any] = data["tool"]["poe"]["tasks"]
    return tasks


def _gate_steps() -> list[str]:
    tasks = _tasks()
    refs: list[str] = [step["ref"] for step in tasks["check"]["sequence"] if "ref" in step]
    return refs


def test_every_ruff_step_the_gate_runs_is_uncached() -> None:
    tasks = _tasks()
    ruff_steps = {
        ref: tasks[ref]["cmd"]
        for ref in _gate_steps()
        if "cmd" in tasks[ref] and tasks[ref]["cmd"].startswith("ruff ")
    }
    assert ruff_steps, "the gate runs ruff"
    for ref, cmd in ruff_steps.items():
        assert "--no-cache" in cmd.split(), f"{ref}: {cmd!r} trusts the metadata-keyed ruff cache"
