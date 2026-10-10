#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# Everything the PUBLISHED init prompt itself promises, graded as world state and never as output
# text (this runner captures no transcript -- see evals/run.py's own docstring). Exit 0 = passed.
# Run with cwd set to the scaffolded fixture copy, from a case's graders/verify.sh, with $1 naming
# the service boundary that case's fixture defines and $2 -- for a registry case, or "checkout" for
# a case whose harness copied this checkout's pages in -- naming who put skill pages in the project
# before the agent started, which step 3's gate needs to read its start state correctly. $3 and $4,
# for a project whose program is a web server, name its ASGI app (module:app) and a route with
# {id}: step 6 then starts the server and grades each request's own trace (run_the_server.py).
#
# Shared by every case whose prompt.md IS the published prompt -- the two init-prompt cases and the
# two registry cases -- so that what "the prompt worked" means is defined once. A registry case adds
# its own registry-only gates first (grade_the_registry.sh) and then delegates the whole of the
# prompt to this script: the prompt is the same text in all four, so a second copy of its grading
# would be a second thing to keep in step.
#
# What is graded, in the order that fails cheapest first:
#
#   1. pyproject.toml declares NarrativeTrace as a dependency.
#   2. Step 3's human gate, in either of D13's two accepted outcomes (run_the_install_gate.sh).
#   3. Step 6: the project RUNS and its own standard output carries a rendered trace naming $1 --
#      or, for a server, each request's output carries its own.
#   4. Step 5: a test asserts [REDACTED] for a deny-listed parameter, and the suite passes it.
#   5. One of the prompt's own four rules: no .received.nt was left on disk.
#   6. A fully green doctor report -- every finding, with config.skills-installed graded only on
#      the applied branch (D13: the prompt permits stopping at the diff).
set -e

service="$1"
registry="$2"
server_app="$3"
server_route="$4"
if [ -z "$service" ]; then
  echo "usage: grade_the_prompt.sh <TracedServiceName> [registry|checkout] [module:app route]" >&2
  exit 1
fi
here=$(dirname "$0")

uv run python -c '
import tomllib
with open("pyproject.toml", "rb") as f:
    doc = tomllib.load(f)
deps = doc.get("project", {}).get("dependencies", [])
if not any(dep.split(">=")[0].split("==")[0].split("[")[0].strip() == "narrativetrace" for dep in deps):
    raise SystemExit("expected pyproject.toml to declare narrativetrace as a dependency")
'

# Step 3 of the prompt: the installer's human gate, D13's two accepted outcomes.
gate_file="$(mktemp)"
trap 'rm -f "$gate_file"' EXIT
sh "$here/run_the_install_gate.sh" "$gate_file" "$registry"
install_state="$(cat "$gate_file")"

# Step 6 of the prompt, graded where the prompt puts it: the program's own output.
if [ -n "$server_app" ]; then
  python3 -I "$here/run_the_server.py" "$service" "$server_app" "$server_route"
else
  sh "$here/run_the_program.sh" "$service"
fi

# Step 5 of the prompt: a test proves the redaction, and the suite actually passes it.
sh "$here/run_the_redaction_test.sh"

# One of the prompt's own four rules, as world state rather than as a promise.
if find . -name "*.received.nt" | grep -q .; then
  echo "the prompt says not to commit .received.nt files; one was left on disk" >&2
  exit 1
fi

# `narrativetrace doctor` exits non-zero when ANY finding fails, so its exit code must not end
# the script under `set -e` -- the report itself is what is graded, and an empty one still fails
# the parse below. The prompt's own step 5 exists so this report can be FULLY green, redaction
# proof included — every finding must hold except config.skills-installed on the previewed branch,
# where "not installed" is the truthful, expected reading (D13: graded on the applied branch only).
report="$(uv run narrativetrace doctor --json || true)"
echo "$report" | NT_INIT_STATE="$install_state" uv run python -c '
import json, os, sys
report = json.load(sys.stdin)
install_state = os.environ["NT_INIT_STATE"]
def graded(finding):
    return install_state == "applied" or finding["id"] != "config.skills-installed"
bad = {f["id"]: f["status"] for f in report["findings"] if f["status"] != "pass" and graded(f)}
if bad:
    print("expected every doctor finding to be green:", json.dumps(bad), file=sys.stderr)
    sys.exit(1)
print("grade_the_prompt.sh: the published init prompt produced a running trace, a proven redaction, and a fully green doctor report")
'
