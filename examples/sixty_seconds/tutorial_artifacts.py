# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Generates the "See a trace in 60 seconds" tutorial's two captured-output artifacts.

Shared by ``test_sixty_seconds.py`` (which also asserts on the returned content) and
``packages/narrativetrace/tests/test_snippet_check.py``'s ``TestRealRepository`` (which only
needs the files on disk before it checks the whole repository for snippet drift). Both call
``write_artifacts()`` themselves rather than relying on the other having already run: pytest
collects ``packages`` before ``examples`` (``testpaths`` in ``pyproject.toml``), so
``TestRealRepository`` cannot assume this module's test has run first, and a pristine checkout
(the publish script's cold ``git archive`` verify) has no pre-existing ``build/`` at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
BUILD_DIR = HERE / "build"

PLAIN_ARTIFACT = "see_a_trace.txt"
WITH_LOGGER_ARTIFACT = "see_a_trace_with_logger.txt"


def _run_script(name: str) -> str:
    """Runs ``name`` as a real, separate process -- exactly what ``uv run <name>`` does -- and
    returns what it printed.

    Pins UTF-8 on both ends of the pipe rather than trusting ``text=True``'s locale-derived
    default -- found running this inside `poe check`'s own subprocess environment (never bare
    `uv run pytest`; the difference is environment-dependent, rule 8's exact target):
    ``locale.getpreferredencoding()`` resolves to ``US-ASCII`` there, not UTF-8, which chokes the
    instant this script's own "→"/"—" output crosses the pipe. ``PYTHONIOENCODING`` protects the
    child's *encode* side the same way ``encoding="utf-8"`` protects this call's *decode* side --
    belt and braces, since only one side actually failed here but either could, elsewhere.
    """
    result = subprocess.run(  # nosec B603 - fixed argv, no shell, no untrusted input
        [sys.executable, name],
        cwd=HERE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout


def _save(filename: str, content: str) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / filename).write_text(content, encoding="utf-8")


def write_artifacts() -> tuple[str, str]:
    """Runs ``main.py`` and ``main_with_logger.py``, saves their stdout under ``build/`` for
    ``scripts/snippet_check.py`` to embed, and returns ``(plain, with_logger)`` -- idempotent
    and safe to call from more than one test."""
    plain = _run_script("main.py")
    _save(PLAIN_ARTIFACT, plain)

    with_logger = _run_script("main_with_logger.py")
    _save(WITH_LOGGER_ARTIFACT, with_logger)

    return plain, with_logger
