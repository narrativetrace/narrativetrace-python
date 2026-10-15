#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# Transcript verifier for the fresh session AFTER THE PUBLISHED PROMPT. Exit 0 = gate passed.
# Run with cwd set to the scaffolded fixture copy; $NARRATIVETRACE_TRANSCRIPT points at this
# trial's evidence, which lives outside this project.
#
# THE CASE
#
# Turn 1 is the published init prompt, byte for byte (test_init_prompt_drift.py enforces that): the
# agent installs NarrativeTrace and stops at the diff the prompt asks it to show; turn 2 approves
# the diff, so the skills are really installed. Turn 3 is a NEW SESSION in the
# same project (case.json: "freshTurns": [3]) that asks a doctor-shaped question. What is graded is
# what that second session FINDS: its init event must list every NarrativeTrace skill, and it must
# reach for the doctor -- the skill by name, or the doctor command itself.
#
# WHY A SECOND CASE
#
# fresh-session-sees-the-skills lets the harness run this checkout's installer and measures only
# what a later session finds. This one keeps the agent's own install in the loop -- the whole real
# path -- so it is the case that catches an agent stopping before the install. A red here with the
# other case green is the prompt path, not the installer.
#
# WHY A FRESH SESSION
#
# Benchmark shakedown run 4 (2026-10-10, item 166): the install wrote `.agents/skills` and the
# `AGENTS.md` section, the doctor reported the skills installed, and the next Claude Code session
# listed no NarrativeTrace skill -- it loads `.claude/skills` only, which the installer wrote just
# where a `.claude/` directory or a `CLAUDE.md` already existed. The install cases grade the
# session that ran the install, where that gap is invisible by construction.
set -e

python3 "$(dirname "$0")/../../grade_the_fresh_session.py"
