#!/usr/bin/env bash
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# NarrativeTrace demo launcher — one command, the trace story front and center.
#
#   ./demo.sh                                interactive example picker
#   ./demo.sh --example ecommerce            non-interactive
#   ./demo.sh --example ecommerce --classic  the same run as ordinary timestamped logs
#   ./demo.sh --example ecommerce --no-pause play straight through, no stop points
#   ./demo.sh --example ecommerce --lang es  the same trace, narrated in Spanish (or zh-CN)
#   ./demo.sh --list                         list the examples this launcher can run
#
# On a terminal the demo stops after each scenario — [Enter] continues, q quits — and every
# scenario opens with a note on how its trace is wired. --lang es|zh-CN re-renders the SAME
# recorded run through the example's curated glossary: identifiers and narration translate,
# values stay byte-identical, and uncurated phrases land in a per-scenario gaps footer.
#
# All argument parsing past this point belongs to examples/demo/launcher.py (poe demo); this
# script only makes sure the workspace is installed before handing off to it, so `./demo.sh` is
# the first command a visitor runs, not the third.
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  # 2..15 is the header comment block; 16 is `set -euo pipefail`, which a wider
  # range would print as the trailing line of --help.
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

command -v uv >/dev/null 2>&1 || {
  echo "error: uv is required — https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
}

# Waits for a background child, animating a braille spinner on a TTY (pipes and CI just wait
# quietly). Ctrl-C kills the child rather than orphaning it. Returns the child's exit status so
# the caller can show the buffered log only on failure.
await() {
  local pid="$1" message="$2" frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏' i=0
  trap 'kill "$pid" 2>/dev/null; printf "\n"; exit 130' INT
  if [[ -t 1 ]]; then
    while kill -0 "$pid" 2>/dev/null; do
      printf '\r%s %s' "${frames:i++%10:1}" "$message"
      sleep 0.1
    done
  fi
  trap - INT
  wait "$pid"
}

# A fresh clone has no .venv — narrativetrace-diagrams, narrativetrace-clarity and the rest of
# the workspace arrive only with a full sync. `uv run` alone auto-syncs just the ROOT project's
# own dependency group (narrativetrace core plus dev tooling) — enough for `--list`, not for an
# actual example run (examples/tour.py imports narrativetrace_diagrams), which is exactly the
# bare ModuleNotFoundError a first-run visitor hits without this step. `--frozen`: the demo must
# run exactly what uv.lock pins, never resolve anew.
#
# The stamp (a copy of uv.lock, inside the gitignored .venv) is the node_modules-style "is it
# already installed" check — a uv workspace has no single directory that means "all packages are
# synced" the way node_modules does, so this pins the lockfile bytes a synced .venv was built
# from instead: unchanged since the last successful sync means skip silently, no spinner, no
# `uv` subprocess at all.
SYNC_STAMP=".venv/.narrativetrace-demo-synced"
sync_workspace() {
  [[ -f "$SYNC_STAMP" ]] && cmp -s uv.lock "$SYNC_STAMP" && return
  local log
  if [[ ! -t 1 ]]; then
    echo "Syncing the workspace (uv sync --all-packages, first run only)..."
    uv sync --all-packages --frozen >/dev/null
    cp uv.lock "$SYNC_STAMP"
    return
  fi
  log=$(mktemp)
  uv sync --all-packages --frozen >"$log" 2>&1 &
  if await $! "Syncing the workspace (uv sync --all-packages, first run only)..."; then
    printf '\r✔ Workspace synced.                                             \n'
    cp uv.lock "$SYNC_STAMP"
    rm -f "$log"
  else
    printf '\r✖ Sync failed:                                                  \n'
    cat "$log"
    rm -f "$log"
    exit 1
  fi
}
sync_workspace

exec uv run python -m examples.demo "$@"
