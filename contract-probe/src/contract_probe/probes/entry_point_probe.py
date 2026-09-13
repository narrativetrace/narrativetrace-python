# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Entry-point probe (docs-vs-published-gate §2): proves a PyPI coordinate resolves at exactly
the version claimed. `scripts/contract_check.py` installs every entry-point package into a fresh
venv via `uv run --with <name>==<version> ...` before invoking this probe, so the interesting
failure mode this guards against is not "the network has no answer" (that invocation would already
have failed) but a silently substituted version -- a stale wheel cache, a local editable install
still on `PYTHONPATH` -- standing in for the real, published answer.
"""

from __future__ import annotations

from importlib import metadata


def observe(coordinate: str, expected_version: str) -> str:
    try:
        installed_version = metadata.version(coordinate)
    except metadata.PackageNotFoundError:
        return "MISSING"
    return "PRESENT" if installed_version == expected_version else "MISSING"
