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
# $2, when given, names the REGISTRY that delivered this project's pages (claude-marketplace |
# npx-skills) and relaxes exactly one thing: "previewed" no longer requires an empty
# .agents/skills, because the registry put both pages there before the agent started. A registry
# case's own evidence about adoption is not this gate at all -- it is grade_the_registry.sh's plan
# with zero refusals, which holds in BOTH branches. What stays strict is the middle: exactly one
# page stamped is a half-applied install in either mode.
#
# Writes the outcome ("applied" or "previewed") to $1 so the caller's own doctor check can grade
# config.skills-installed only on the applied branch (D13) -- exit status alone cannot carry that,
# and this script runs as a child process, so an environment variable set here would not survive
# back to the caller's shell either.
set -e

outfile="$1"
registry="$2"
if [ -z "$outfile" ]; then
  echo "usage: run_the_install_gate.sh <outcome-file> [registry]" >&2
  exit 1
fi

provenance="<!-- installed by narrativetrace init from"
doctor_page=".agents/skills/narrativetrace-doctor/SKILL.md"
setup_page=".agents/skills/add-narrative-tracing/SKILL.md"

stamped=0
for page in "$doctor_page" "$setup_page"; do
  if [ -f "$page" ] && grep -qF "$provenance" "$page"; then
    stamped=$((stamped + 1))
  fi
done

nothing_installed=1
if [ -d .agents/skills ] || grep -qF "narrativetrace:start" AGENTS.md 2>/dev/null; then
  nothing_installed=0
fi

if [ "$stamped" = "2" ]; then
  echo "applied" >"$outfile"
  echo "run_the_install_gate.sh: step 3 was applied -- both skill pages carry our provenance"
elif [ "$stamped" != "0" ]; then
  echo "step 3's install stamped only one of the two skill pages -- a half-applied install is not one of the two outcomes the prompt permits" >&2
  exit 1
elif [ "$nothing_installed" = "1" ]; then
  echo "previewed" >"$outfile"
  echo "run_the_install_gate.sh: step 3 was left at preview -- nothing installed, which the prompt allows"
elif [ -n "$registry" ]; then
  echo "previewed" >"$outfile"
  echo "run_the_install_gate.sh: step 3 was left at preview -- the $registry pages are there, none of them ours"
else
  echo "step 3's install is neither fully applied (both pages, our provenance) nor left at preview (nothing written) -- a half-applied install is not one of the two outcomes the prompt permits" >&2
  exit 1
fi
