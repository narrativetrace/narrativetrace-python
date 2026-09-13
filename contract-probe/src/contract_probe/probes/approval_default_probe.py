# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-approval-default`: approval mode is opt-in -- `NARRATIVETRACE_APPROVAL` defaults to
`false`, and a reviewed received trace promotes via `narrativetrace-approve` --
documentation/what-to-commit.md `#approval-mode-visually`.

A passing test with no committed baseline must write no approval bookkeeping artifact at all
(never `.received.nt`, never an auto-written `.approved.nt`) when approval mode is left at its
default. `NARRATIVETRACE_OUTPUT` is forced on for this probe's own setup only, so it observes
approval specifically rather than the separately-tested output-on-by-default claim;
`NARRATIVETRACE_APPROVAL` itself is left unset -- that absence IS the claim under test.
"""

from __future__ import annotations

from contract_probe.pytest_fixture_support import run_traced_fixture

_APPROVAL_SUFFIXES = (".received.nt", ".approved.nt", ".incomplete.nt")


def observe() -> str:
    work_dir = run_traced_fixture(env={"NARRATIVETRACE_OUTPUT": "true"})
    output_dir = work_dir / "narrative-traces"
    approved_dir = work_dir / "test-narratives"
    for directory in (output_dir, approved_dir):
        if directory.is_dir() and any(
            path.name.endswith(_APPROVAL_SUFFIXES) for path in directory.rglob("*")
        ):
            return "true"
    return "false"
