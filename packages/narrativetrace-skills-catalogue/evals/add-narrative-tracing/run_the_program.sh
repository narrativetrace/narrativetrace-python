#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# Grades the published init prompt's step 6 -- "Run the program" -- as world state: the project the
# agent left behind RUNS, and its own standard output carries a rendered trace naming $1, the
# service boundary this case's fixture defines. Shared by both init-prompt cases; run with cwd set
# to the scaffolded fixture copy, from a case's graders/verify.sh.
#
# Why the program's stdout and not a file: the prompt sends the reader to llms.txt's "Install and
# first trace" block, which renders the trace with IndentedTextRenderer and PRINTS it, then runs it
# with `uv run main.py`. A rendered `.md` under the output directory is the OTHER path (the pytest
# plugin writing test-time artifacts), which this prompt never asks for -- grading that failed both
# of Java's cases on agents that had done exactly what was asked (2026-09-25).
set -e

service="$1"
if [ -z "$service" ]; then
  echo "usage: run_the_program.sh <TracedServiceName>" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
log="$work/program-output.txt"

# The entry point the install block itself describes, then the one the fixture shipped, then any
# single script that both captures and prints a trace. The agent's layout is the agent's work: a
# grader never renames a file to make its own assertion easier.
entry_point() {
  for candidate in main.py app.py; do
    [ -f "$candidate" ] && { printf '%s' "$candidate"; return 0; }
  done
  found=$(grep -rl "capture_trace()" --include="*.py" . 2>/dev/null | grep -v '/\.venv/' | head -1)
  [ -n "$found" ] && { printf '%s' "$found"; return 0; }
  return 1
}

program=$(entry_point) || {
  echo "no runnable entry point -- the prompt's \"Run the program\" step has nothing to run" >&2
  exit 1
}

# Bounded, always: a cold run resolves and downloads the packages, and a program that hangs has to
# fail this case rather than the whole harness.
if ! timeout 900 uv run "$program" >"$log" 2>&1; then
  echo "\`uv run $program\` failed -- the prompt says to run the program and read its output" >&2
  cat "$log" >&2
  exit 1
fi

# A rendered trace line is `<Service>.<method>(...)`, whatever renderer produced it; the leading
# guard keeps `MyOrderService.` from passing for `OrderService`.
if ! grep -Eq "(^|[^A-Za-z0-9_])${service}\.[A-Za-z_][A-Za-z0-9_]*\(" "$log"; then
  echo "expected the program's own output to carry a rendered trace line naming $service" >&2
  echo "--- what it printed instead ---" >&2
  cat "$log" >&2
  exit 1
fi

echo "run_the_program.sh: the program ran and printed a rendered trace naming $service"
