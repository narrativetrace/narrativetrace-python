# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-run-name-manifest-field`: `manifest.json` carries a top-level `run` object naming the
run this manifest belongs to -- documentation/guides/configuration.md `#the-run-has-a-name`.
`NARRATIVETRACE_OUTPUT` is this probe's own setup, matching `manifest_identity_probe`.
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
    run = document.get("run") if isinstance(document, dict) else None
    ok = (
        isinstance(run, dict)
        and isinstance(run.get("id"), str)
        and isinstance(run.get("name"), str)
    )
    return "true" if ok else "false"
