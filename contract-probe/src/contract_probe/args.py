# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Parsed command-line arguments for `contract_probe.runner`."""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Args:
    version: str
    contract_path: str
    out_path: str | None


def parse(argv: list[str]) -> Args:
    parser = argparse.ArgumentParser(prog="contract-probe")
    parser.add_argument(
        "--version", required=True, help="the published version under test (e.g. 0.1.1)"
    )
    parser.add_argument(
        "--contract",
        dest="contract_path",
        default="documentation/contract.yaml",
        help="path to documentation/contract.yaml",
    )
    parser.add_argument(
        "--out", dest="out_path", default=None, help="write a JSON result to this path"
    )
    parsed = parser.parse_args(argv)
    return Args(
        version=parsed.version, contract_path=parsed.contract_path, out_path=parsed.out_path
    )
