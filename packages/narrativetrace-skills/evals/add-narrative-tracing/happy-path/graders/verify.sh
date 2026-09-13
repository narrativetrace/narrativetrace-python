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

report="$(uv run narrativetrace doctor --json)"
echo "$report" | uv run python -c '
import json, sys
report = json.load(sys.stdin)
bad = [f for f in report["findings"] if f["id"].startswith("toolchain.") and f["status"] != "pass"]
if bad:
    print("expected every toolchain.* finding to hold:", json.dumps(bad), file=sys.stderr)
    sys.exit(1)
print("verify.sh: cold install produced a working project with a clean toolchain")
'
