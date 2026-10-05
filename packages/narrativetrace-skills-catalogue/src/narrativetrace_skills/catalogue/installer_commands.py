# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The installer's adopter-facing command literal, beside :mod:`doctor_commands` -- one home per
concept, so a second hand-copied literal is a duplication-ratchet failure rather than a silent
divergence.

INTENT (mirrors the Java reference's own ``InstallerCommands``): a skill may PREVIEW the install
and may never apply it. The preview is the whole safety property -- ``init`` writes into
``AGENTS.md`` and ``.agents/skills/``, and the approval for that is structural: a person reads the
diff and runs the command again without the flag. That is why only the previewing form is a
constant here; the applying form (``narrativetrace init``, no ``--dry-run``) is deliberately not
available to a step.

Every embedded ``python -c`` script here uses double quotes only, never single: the whole script
is itself wrapped in single quotes for the shell (``uv run python -c '...'``, matching
``doctor_commands.py``'s own convention), so a single quote inside it would close that wrapper
early.
"""

from __future__ import annotations

PREVIEW_INSTALL = "uv run narrativetrace init --dry-run"
"""Previews what ``narrativetrace init`` would write, and writes nothing -- this port's own
``--dry-run`` flag, never Gradle's built-in one, so nothing shadows it (verified empirically,
Phase 3 milestone 3)."""

_CHECK_PREVIEW_WROTE_NOTHING = """\
import pathlib, subprocess, sys
result = subprocess.run(
    ["uv", "run", "narrativetrace", "init", "--dry-run"], capture_output=True, text=True
)
shown = (
    "action(s)" in result.stdout
    and ".agents/skills" in result.stdout
    and "AGENTS.md" in result.stdout
)
untouched = not pathlib.Path(".agents/skills").exists() and not pathlib.Path("AGENTS.md").exists()
sys.exit(0 if result.returncode == 0 and shown and untouched else 1)
"""

VERIFY_PREVIEW_WROTE_NOTHING = f"uv run python -c '{_CHECK_PREVIEW_WROTE_NOTHING}'"
"""The preview's definition of done: a plan naming both ``.agents/skills`` and ``AGENTS.md`` was
shown, and neither exists on disk afterward -- nothing is written until the same command runs
again without ``--dry-run``. Re-runs the preview itself (rather than trusting the step's own
``commands``) so this is provably what a person would see, not a second, drifting copy of it."""
