# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`config-shape-narrativetrace-doctor`: `narrativetrace doctor --json` emits a well-formed report
(parses, carries all eleven finding ids) -- documentation/agent-skills.md
`#the-narrativetrace-cli`.

The import is deferred into `observe()` rather than sitting at module level: `contract_probe.
runner` imports every probe module together, and this runner can be pointed at an OLDER published
artifact (`python -m scripts.contract_check <version>`), whose public API may not carry the
`narrativetrace.doctor` package at all -- a module-level import of it would then break every OTHER
probe's import too, not just this one's (see `export_to_logger_probe.py` for the pattern).

Calls `narrativetrace.doctor.cli_bin.main` in-process (never a subprocess) against the current
working directory -- whatever project `contract-probe` itself runs from (its own `pyproject.toml`
satisfies the CLI's "readable pyproject.toml" precondition) -- and reads the JSON `main` prints to
stdout. The claim under test is the report's SHAPE, never any individual finding's pass/fail
value, which legitimately varies by project.
"""

from __future__ import annotations

import contextlib
import io
import json


def observe() -> str:
    from narrativetrace.doctor.cli_bin import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = main(["doctor", "--json"])
    if exit_code not in (0, 1):
        return "malformed"
    try:
        report = json.loads(buffer.getvalue())
    except json.JSONDecodeError:
        return "malformed"
    findings = report.get("findings")
    if not isinstance(findings, list) or len(findings) != 11:
        return "malformed"
    return "well-formed"
