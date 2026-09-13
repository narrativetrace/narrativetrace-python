# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Reads `documentation/contract.yaml` -- the schema itself is validated per commit by
`scripts/contract_lint.py` (wired into `poe check`); this reader trusts that and only extracts
what `contract_probe.runner` needs to run.

Deliberately a separate reader, not an import of `scripts.contract_lint`: this project consumes
only published PyPI packages and can never depend on the main repository's own `scripts/` package,
which is not itself published (mirrors Java's `contract-probe/.../ContractYaml.java`, kept apart
from buildSrc's `ContractLintSupport.kt` twin for the same reason).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ContractEntry:
    """Mirrors `scripts.contract_lint.ContractEntry` field-for-field (see that module's docstring
    for what `expect` folds together)."""

    id: str
    kind: str
    page: str
    claim: str
    since: str
    expect: str
    probe: str
    coordinate: str | None
    registry: str | None


def _entry_from_raw(raw: dict[str, Any]) -> ContractEntry:
    expect = raw.get("documented_default") or raw.get("expected_effect")
    return ContractEntry(
        id=raw["id"],
        kind=raw["kind"],
        page=raw["page"],
        claim=raw["claim"],
        since=raw["since"],
        expect=expect,
        probe=raw["probe"],
        coordinate=raw.get("coordinate"),
        registry=raw.get("registry"),
    )


def read(path: Path) -> list[ContractEntry]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [_entry_from_raw(raw) for raw in document["entries"]]
