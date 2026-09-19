# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Guards `runner._DISPATCH` against silently missing an entry -- catches exactly the gap that
crashed the nightly contract check on 2026-09-18 (`probed-run-name-console-footer` and
`probed-run-name-manifest-field` were added to `documentation/contract.yaml` on 2026-09-13
without a matching dispatch registration, so the check died with `RuntimeError` instead of
failing a test)."""

from __future__ import annotations

from pathlib import Path

from contract_probe import runner
from contract_probe.contract_yaml import read

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = _REPO_ROOT / "documentation" / "contract.yaml"


def _missing_dispatch_ids(contract_path: Path) -> list[str]:
    entries = read(contract_path)
    return [
        entry.id
        for entry in entries
        if entry.id not in runner._ENTRY_POINT_IDS and entry.id not in runner._DISPATCH
    ]


def test_every_dispatchable_entry_in_contract_yaml_has_a_registered_probe() -> None:
    """Derived from the real `documentation/contract.yaml`, not a hardcoded id list: every entry
    whose kind is not entry-point (those dispatch via `entry_point_probe`, keyed by
    `runner._ENTRY_POINT_IDS`) must have a matching callable in `runner._DISPATCH`, or
    `runner._observe` raises `RuntimeError` at check time instead of a test catching it first."""
    assert _missing_dispatch_ids(_CONTRACT_PATH) == []


def test_a_bogus_entry_without_a_dispatch_is_caught(tmp_path: Path) -> None:
    """Proves the guard above is not vacuously true: a scratch contract.yaml carrying an entry id
    that was never registered in `runner._DISPATCH` must actually fail the same assertion."""
    scratch = tmp_path / "contract.yaml"
    scratch.write_text(
        """
        version_source: "pyproject.toml#version"
        entries:
          - id: probed-bogus-entry-nobody-registered
            kind: probed-default
            page: "documentation/foo.md#anchor"
            claim: "a bogus claim used only to prove the dispatch guard fires"
            since: "0.1.2"
            documented_default: "true"
            probe: "contract-probe/src/contract_probe/probes/does_not_exist_probe.py"
        """,
        encoding="utf-8",
    )

    assert _missing_dispatch_ids(scratch) == ["probed-bogus-entry-nobody-registered"]
