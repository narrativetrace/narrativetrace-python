#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier. Exit 0 = gate passed. Run with cwd set to the scaffolded fixture copy.
set -e

report="$(uv run narrativetrace doctor --json)"
echo "$report" | uv run python -c '
import json, sys
report = json.load(sys.stdin)
by_id = {f["id"]: f for f in report["findings"]}
finding = by_id.get("trap.redaction-proof")
if finding is None or finding["status"] != "fail":
    print("expected trap.redaction-proof to fail on the redaction-gap fixture", file=sys.stderr)
    sys.exit(1)
print("verify.sh: doctor correctly flags the unproven redaction")
'
