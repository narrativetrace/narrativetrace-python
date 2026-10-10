#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier for the PUBLISHED init prompt against an existing FastAPI service (Phase 6
# D4: the doctor as the run-time oracle). Exit 0 = gate passed. Run with cwd set to the scaffolded
# fixture copy. The fixture and why: ../../../fixtures/fastapi-service/README.md.
#
# The prompt never says FastAPI. What this case adds to grade_the_prompt.sh (which grades everything
# the prompt itself promises, here with a server as the program and this checkout's pages copied in):
#
#   1. The fixture's own service and route are still there -- the prompt says to trace a REAL
#      service boundary, never a demo beside it.
#   2. config.asgi-middleware is present in the doctor's report and passes: the agent wired
#      narrativetrace-asgi because the doctor said so.
#   3. Step 6 for a server: each of two requests prints its own trace (run_the_server.py).
#
# case.json scripts the user's second turn -- the reply to step 3's diff -- so the framework wiring,
# all of which comes after that gate, is reached at all.
set -e
here="$(dirname "$0")"

for file in billing/invoice_service.py billing/api.py; do
  test -f "$file" || {
    echo "the fixture's existing implementation must still be there: $file" >&2
    exit 1
  }
done

report="$(mktemp)"
trap 'rm -f "$report"' EXIT
uv run narrativetrace doctor --json >"$report" || true
python3 -I -c '
import json, sys
try:
    findings = {f["id"]: f for f in json.load(open(sys.argv[1]))["findings"]}
except ValueError:
    sys.exit("expected a doctor report -- narrativetrace doctor did not run in this project")
asgi = findings.get("config.asgi-middleware")
if asgi is None or asgi["status"] != "pass":
    print("expected config.asgi-middleware to pass:", json.dumps(asgi), file=sys.stderr)
    sys.exit(1)
print("verify.sh: config.asgi-middleware passes --", asgi["message"])
' "$report"

sh "$here/../../grade_the_prompt.sh" InvoiceService checkout billing.api:app "/invoices/{id}"
