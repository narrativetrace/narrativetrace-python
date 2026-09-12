# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Rewrites drifted snippet blocks in place (`poe snippet-sync`; check logic in
`scripts/snippet_check.py`, wired into `poe check`).

English pages only, same as `translation_check.py`'s own split between staleness (checked) and
translated code-block content (never auto-rewritten) — a translated mirror's fix is a translator
restamping its header after this runs on the English source.

Also refreshes `documentation/llms.txt`'s docs-vs-published banner line (`scripts/llms_banner.py`)
in the same pass, so the two build steps that decide what an agent reads first never drift apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.llms_banner import sync_banner
from scripts.snippet_check import REPO_ROOT, sync_repository


def main() -> int:
    changes = sync_repository(REPO_ROOT)
    banner_change = sync_banner(REPO_ROOT)
    if banner_change is not None:
        changes.append(banner_change)
    if not changes:
        print("snippet-sync: nothing to do — every embedded block already matches its source")
        return 0
    print("snippet-sync: resynced the following blocks from their source:")
    for change in changes:
        print(f"  {change}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
