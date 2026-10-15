# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The command of ``narrativetrace-explain`` that is its own, in the closed ``uv``/``git``
vocabulary. Mirrors Java's ``ExplainCommands``.

It is what an ADOPTER runs in their own project; ``tests/test_replay_fixture.py`` maps it onto the
``examples/sixty_seconds`` fixture for Tier A2 replay. The two trace-listing commands the explain
loop shares with the verify and debug loops are
:mod:`~narrativetrace_skills.catalogue.verify_commands`' own.
"""

from __future__ import annotations

RUN_THE_SCENARIO = "uv run pytest <the test that exercises the flow you were asked about>"
"""Runs the one existing test whose traced run is the evidence the explanation reads."""
