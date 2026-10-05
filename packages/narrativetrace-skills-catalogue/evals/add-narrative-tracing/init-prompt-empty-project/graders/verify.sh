#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier for the PUBLISHED init prompt (never output text equality). Exit 0 = gate
# passed. Run with cwd set to the scaffolded fixture copy.
#
# Grades exactly what the prompt promises, and nothing else: a project that declares NarrativeTrace,
# a program that runs and prints a trace, its own rules kept, and a clean doctor report.
set -e

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
sh "$(dirname "$0")/../../run_the_install_gate.sh" "$gate_file"
install_state="$(cat "$gate_file")"

# Step 6 of the prompt, graded where the prompt puts it: the program's own standard output. The
# service name is the one llms.txt'"'"'s own install block builds.
sh "$(dirname "$0")/../../run_the_program.sh" OrderService

# Step 5 of the prompt: a test proves the redaction, and the suite actually passes it.
sh "$(dirname "$0")/../../run_the_redaction_test.sh"

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
print("verify.sh: the published init prompt produced a running trace, a proven redaction, and a fully green doctor report")
'
