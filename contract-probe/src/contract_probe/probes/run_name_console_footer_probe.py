# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-run-name-console-footer`: the console suite footer names the enclosing test-suite run --
a `run: <phrase>` line -- documentation/guides/configuration.md `#the-run-has-a-name`.

`NARRATIVETRACE_OUTPUT` is forced on for this probe's own setup, matching `manifest_identity_probe`.
"""

from __future__ import annotations

import contextlib
import io
import re

from contract_probe.pytest_fixture_support import run_traced_fixture

_RUN_LINE = re.compile(r"^\s*run: [a-z]+ [a-z]+ [a-z]+$")


def observe() -> str:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run_traced_fixture(env={"NARRATIVETRACE_OUTPUT": "true"})
    console = captured.getvalue()
    return "true" if any(_RUN_LINE.match(line) for line in console.splitlines()) else "false"
