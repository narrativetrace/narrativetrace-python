# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Version compare, deliberately duplicated (not shared) from `scripts.contract_lint.is_applicable`:
this project consumes only published PyPI packages and can never depend on the main repository's
own `scripts/` package, which is not itself published. Both sides are unit tested against the
same cases (docs-vs-published-gate §5.1 ruling 1)."""

from __future__ import annotations


def _parts(version: str) -> list[int]:
    return [int(part) for part in version.split(".")]


def is_applicable(since: str, installed_version: str) -> bool:
    """True while `since` is NOT strictly later than `installed_version`."""
    since_parts = _parts(since)
    installed_parts = _parts(installed_version)
    for i in range(max(len(since_parts), len(installed_parts))):
        x = since_parts[i] if i < len(since_parts) else 0
        y = installed_parts[i] if i < len(installed_parts) else 0
        if x != y:
            return x < y
    return True
