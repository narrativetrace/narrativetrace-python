#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier (never output text equality). Exit 0 = gate passed. Run with cwd set to the
# scaffolded fixture copy.
set -e

uv run python -c '
import tomllib
with open("pyproject.toml", "rb") as f:
    doc = tomllib.load(f)
deps = doc.get("project", {}).get("dependencies", [])
if not any(dep.split(">=")[0].split("==")[0].strip() == "narrativetrace" for dep in deps):
    raise SystemExit("expected pyproject.toml to declare narrativetrace as a dependency")
'

# The premise this case sets: an empty project, no tests. What the agent leaves behind is a runnable
# demo whose run PRINTS a trace -- the grader runs it itself and reads its stdout; the demo's name
# is read from the tree (the page's own main.py, else any script that captures a trace), never
# from a transcript, and a layout is never renamed to make this assertion easier.
. "$(dirname "$0")/../../bounded.sh"
demo=""
if [ -f main.py ]; then
  demo=main.py
else
  demo=$(grep -rl "capture_trace()" --include="*.py" . 2>/dev/null | grep -v '/\.venv/' | head -1)
fi
[ -n "$demo" ] || { echo "no demo script left behind: expected main.py or a script that captures a trace" >&2; exit 1; }
log=$(mktemp)
trap 'rm -f "$log"' EXIT
bounded 900 uv run python "$demo" >"$log" 2>&1 || {
  echo "\`uv run python $demo\` failed:" >&2
  cat "$log" >&2
  exit 1
}
grep -Eq '^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\(' "$log" || {
  echo "expected the demo's output to carry a rendered traced call line (Class.method(...)); it printed:" >&2
  cat "$log" >&2
  exit 1
}

# `narrativetrace doctor` exits non-zero when ANY finding fails, including ones this case
# does not gate on, so its exit code must not end the script under `set -e` -- the report
# itself is what is graded, and an empty one still fails the parse below.
report="$(uv run narrativetrace doctor --json || true)"
echo "$report" | uv run python -c '
import json, sys
report = json.load(sys.stdin)
bad = [f for f in report["findings"] if f["id"].startswith("toolchain.") and f["status"] != "pass"]
if bad:
    print("expected every toolchain.* finding to hold:", json.dumps(bad), file=sys.stderr)
    sys.exit(1)
print("verify.sh: cold install produced a working project with a clean toolchain")
'
