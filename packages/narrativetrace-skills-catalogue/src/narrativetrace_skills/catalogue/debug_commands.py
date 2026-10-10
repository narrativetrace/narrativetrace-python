# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The commands of ``narrativetrace-debug``, in the closed ``uv``/``git`` vocabulary. Mirrors Java's
``DebugCommands``.

Each command is what an ADOPTER runs in their own project; ``tests/test_replay_fixture.py`` maps
each onto the ``examples/sixty_seconds`` fixture for Tier A2 replay. The trace-listing commands the
debug loop shares with the verify loop are
:mod:`~narrativetrace_skills.catalogue.verify_commands`' own.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue.verify_commands import list_files

REPRODUCE = "uv run pytest <the test that reproduces the symptom>"
"""Runs the one test that drives the reported input through the real path, tracing on."""

LIST_DIAGRAMS = list_files("narrative-traces/diagrams", "*.mmd")
"""Lists the sequence diagrams the run wrote — ordering across components, threads and tasks."""
