# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from contract_probe.args import parse


def test_parse_requires_version() -> None:
    args = parse(["--version=0.1.1"])
    assert args.version == "0.1.1"
    assert args.contract_path == "documentation/contract.yaml"
    assert args.out_path is None


def test_parse_reads_contract_and_out() -> None:
    args = parse(["--version=0.1.1", "--contract=foo.yaml", "--out=result.json"])
    assert args.contract_path == "foo.yaml"
    assert args.out_path == "result.json"
