# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from pathlib import Path

from contract_probe.contract_yaml import read


def test_read_parses_an_entry_point_entry(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(
        """
        version_source: "pyproject.toml#version"
        entries:
          - id: entry-point-narrativetrace
            kind: entry-point
            registry: pypi
            coordinate: "narrativetrace"
            page: "documentation/foo.md#anchor"
            claim: "narrativetrace resolves"
            since: "0.1.0"
            documented_default: "PRESENT"
            probe: "contract-probe/src/contract_probe/probes/entry_point_probe.py"
        """,
        encoding="utf-8",
    )
    entries = read(contract)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.id == "entry-point-narrativetrace"
    assert entry.coordinate == "narrativetrace"
    assert entry.expect == "PRESENT"


def test_read_accepts_expected_effect_as_the_expect_field(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(
        """
        version_source: "pyproject.toml#version"
        entries:
          - id: config-shape-example
            kind: config-shape
            page: "documentation/foo.md#anchor"
            claim: "an example config shape produces an effect"
            since: "0.1.0"
            expected_effect: "field redacted"
            probe: "probe.py"
        """,
        encoding="utf-8",
    )
    entry = read(contract)[0]
    assert entry.expect == "field redacted"
