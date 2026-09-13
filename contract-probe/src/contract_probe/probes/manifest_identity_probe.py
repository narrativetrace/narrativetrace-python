# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-manifest-per-invocation-identity`: a run writes `<output_dir>/manifest.json`, one row
per traced scenario naming its test, its invocation number and every file it owns --
documentation/structural-trace-format.md `#artifact-identity-cross-platform`.

`NARRATIVETRACE_OUTPUT` is forced on for this probe's own setup: the SEPARATE
output-on-by-default claim is what `pytest_artifacts_default_probe` tests.
"""

from __future__ import annotations

import json

from contract_probe.pytest_fixture_support import run_traced_fixture


def observe() -> str:
    work_dir = run_traced_fixture(env={"NARRATIVETRACE_OUTPUT": "true"})
    manifest_path = work_dir / "narrative-traces" / "manifest.json"
    if not manifest_path.is_file():
        return "false"
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError:
        return "false"
    scenarios = document.get("scenarios") if isinstance(document, dict) else None
    return "true" if isinstance(scenarios, list) and len(scenarios) >= 1 else "false"
