#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# Grades the published init prompt's step 3 -- preview `narrativetrace init --dry-run` and show the
# diff, apply for real only after it has been seen -- as world state (never transcript text: this
# runner captures none, see evals/run.py's own docstring). D13 accepts EITHER outcome:
#
#   applied    both rendered skill pages exist under .agents/skills/ and carry our own provenance
#              line (the installer wrote them for real, after the diff was shown)
#   previewed  neither .agents/skills/ nor the narrativetrace AGENTS.md section exists yet (the
#              agent stopped at the diff, exactly as the prompt's own last sentence permits)
#
# Anything else -- AGENTS.md written with no skill page, a skill page with no provenance line, only
# one of the two pages -- is neither of D13's two accepted outcomes and fails the case: it is not
# evidence the diff was ever shown, and not evidence it was safely applied either.
#
# Writes the outcome ("applied" or "previewed") to $1 so the caller's own doctor check can grade
# config.skills-installed only on the applied branch (D13) -- exit status alone cannot carry that,
# and this script runs as a child process, so an environment variable set here would not survive
# back to the caller's shell either.
set -e

outfile="$1"
if [ -z "$outfile" ]; then
  echo "usage: run_the_install_gate.sh <outcome-file>" >&2
  exit 1
fi

provenance="<!-- installed by narrativetrace init from"
doctor_page=".agents/skills/narrativetrace-doctor/SKILL.md"
setup_page=".agents/skills/add-narrative-tracing/SKILL.md"

both_pages_ours=0
if [ -f "$doctor_page" ] && [ -f "$setup_page" ] \
  && grep -qF "$provenance" "$doctor_page" && grep -qF "$provenance" "$setup_page"; then
  both_pages_ours=1
fi

nothing_installed=1
if [ -d .agents/skills ] || grep -qF "narrativetrace:start" AGENTS.md 2>/dev/null; then
  nothing_installed=0
fi

if [ "$both_pages_ours" = "1" ]; then
  echo "applied" >"$outfile"
  echo "run_the_install_gate.sh: step 3 was applied -- both skill pages carry our provenance"
elif [ "$nothing_installed" = "1" ]; then
  echo "previewed" >"$outfile"
  echo "run_the_install_gate.sh: step 3 was left at preview -- nothing installed, which the prompt allows"
else
  echo "step 3's install is neither fully applied (both pages, our provenance) nor left at preview (nothing written) -- a half-applied install is not one of the two outcomes the prompt permits" >&2
  exit 1
fi
