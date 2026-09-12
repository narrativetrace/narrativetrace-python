# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace-approve`` console entry point: the approve verb of approval mode.

Promotes every reviewed received trace (``*.received.nt``) under the approved directory to its
approved counterpart (``*.approved.nt``) — see :mod:`narrativetrace.output.approval`. Follows the
``narrativetrace-clarity`` CLI's shape: stdlib ``argparse``, ``main(argv=None) -> int`` returning
the process exit code, no third-party CLI framework (the core distribution stays dependency-free).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from narrativetrace.config import ConfigResolver
from narrativetrace.output.approval import promote_received

if TYPE_CHECKING:
    from collections.abc import Sequence

_DEFAULT_APPROVED_DIR = "test-narratives"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="narrativetrace-approve",
        description="Promote reviewed *.received.nt traces to *.approved.nt baselines.",
    )
    parser.add_argument(
        "--approved-dir",
        default=None,
        help="directory holding committed *.approved.nt traces (default: the resolved "
        f"narrativetrace.approved_dir configuration key, else {_DEFAULT_APPROVED_DIR!r})",
    )
    return parser


def _approved_dir(cli_value: str | None) -> Path:
    if cli_value is not None:
        return Path(cli_value)
    resolved = ConfigResolver().resolve("approved_dir", _DEFAULT_APPROVED_DIR)
    return Path(resolved or _DEFAULT_APPROVED_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the approve verb; returns the process exit code (always 0 -- there is nothing here
    that fails the build, only work to report)."""
    args = _build_parser().parse_args(argv)
    root = _approved_dir(args.approved_dir)
    promoted = promote_received(root)
    if not promoted:
        print("No received traces to approve.")
        return 0
    for path in promoted:
        print(f"Approved: {path}")
    return 0
