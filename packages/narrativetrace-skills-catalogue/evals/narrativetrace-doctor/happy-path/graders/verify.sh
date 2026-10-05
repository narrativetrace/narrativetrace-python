#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier (never output text equality). Exit 0 = gate passed. Run with cwd set to the
# scaffolded fixture copy.
set -e

report="$(uv run narrativetrace doctor --json)"
echo "$report" | uv run python -c '
import json, sys
report = json.load(sys.stdin)
findings = report.get("findings")
if not isinstance(findings, list) or len(findings) != 11:
    print("expected 11 findings, got", len(findings) if isinstance(findings, list) else findings, file=sys.stderr)
    sys.exit(1)
print("verify.sh: doctor report is well-formed")
'
