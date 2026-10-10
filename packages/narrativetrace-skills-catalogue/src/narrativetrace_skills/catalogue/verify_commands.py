# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The commands of ``narrativetrace-verify`` (and of the pin it shares with
``narrativetrace-debug``), in the closed ``uv``/``git`` vocabulary.

Each command is what an ADOPTER runs in their own project, against the default directories
(``narrative-traces/`` for a run's artifacts, ``test-narratives/`` for committed baselines);
``tests/test_replay_fixture.py`` maps each onto the ``examples/sixty_seconds`` fixture for Tier A2
replay. Listing a directory goes through ``uv run python`` because ``find`` is outside the
vocabulary.
"""

from __future__ import annotations

RUN_THE_PATH = "uv run pytest <the smallest test that drives the real path>"
"""Runs the one test that drives the changed path; the pytest plugin traces it by default."""

RUN_THE_SUITE = "uv run pytest"
"""Runs the whole suite — what approval mode compares, every traced test at once."""

RUN_THE_SUITE_FOR_REVIEW = "uv run pytest || true"
"""The suite as the approval run: ``|| true`` because the first approval run of a test with no
baseline fails ON PURPOSE — that failure is what writes its ``.received.nt``."""


def list_files(directory: str, pattern: str) -> str:
    """A `uv run python` one-liner printing every file under `directory` matching `pattern`."""
    script = (
        f'import pathlib; print(*sorted(pathlib.Path("{directory}").rglob("{pattern}")), sep="\\n")'
    )
    return f"uv run python -c '{script}'"


LIST_STRUCTURAL = list_files("narrative-traces/structural", "*.nt")
"""Lists the value-free structural traces the run wrote."""

LIST_NARRATIVES = list_files("narrative-traces/traces", "*.md")
"""Lists the value-bearing Markdown narratives the run wrote."""

LIST_RECEIVED = list_files("test-narratives", "*.received.nt")
"""Lists the review copies an approval-mode run wrote beside the baselines."""

APPROVE = "uv run narrativetrace-approve"
"""Promotes every reviewed ``.received.nt`` to its ``.approved.nt`` baseline — the pinning."""

_APPROVAL_ON_SCRIPT = (
    "import sys; from narrativetrace.config import ConfigResolver; "
    'value = (ConfigResolver().resolve("approval", "") or "").strip().lower(); '
    'sys.exit(0 if value in {"1", "true", "yes", "on"} else 1)'
)

APPROVAL_MODE_IS_ON = f"uv run python -c '{_APPROVAL_ON_SCRIPT}'"
"""Exits 0 only when approval mode is on as the pytest plugin reads it: ``NARRATIVETRACE_APPROVAL``,
then the ``approval`` key of ``[tool.narrativetrace]``/``narrativetrace.toml``, truthy as the
plugin's ``_truthy`` reads it."""
