#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier (never output text equality). Exit 0 = gate passed. Run with cwd set to the
# scaffolded fixture copy.
#
# The premise this case sets: a project WITH tests. The page's first trace is one existing test run
# through the test integration, so the files the other skills read must exist afterwards: the
# grader runs the project's tests itself, then looks for a `.md` AND a `.nt` under the
# integration's output directory (narrative-traces, the plugin's default).
set -e
. "$(dirname "$0")/../../bounded.sh"

test -f tests/test_invoice_service.py || {
  echo "the fixture's own test must still be there" >&2
  exit 1
}

log=$(mktemp)
trap 'rm -f "$log"' EXIT
bounded 900 uv run pytest -q >"$log" 2>&1 || {
  echo "\`uv run pytest -q\` failed -- the project's own tests must pass:" >&2
  cat "$log" >&2
  exit 1
}

out=narrative-traces
for extension in md nt; do
  found=$(find "$out" -name "*.$extension" -type f 2>/dev/null | head -1)
  [ -n "$found" ] || {
    echo "expected at least one .$extension file under $out/ -- the first trace of an existing test is meant to leave files" >&2
    exit 1
  }
done

# `narrativetrace doctor` exits non-zero when ANY finding fails, including ones this case does not
# gate on; the report is what is graded, and an empty one still fails the parse below.
report="$(uv run narrativetrace doctor --json || true)"
echo "$report" | uv run python -c '
import json, sys
report = json.load(sys.stdin)
bad = [f for f in report["findings"] if f["id"].startswith("toolchain.") and f["status"] != "pass"]
if bad:
    print("expected every toolchain.* finding to hold:", json.dumps(bad), file=sys.stderr)
    sys.exit(1)
print("verify.sh: the existing test left .md and .nt files and the toolchain holds")
'
