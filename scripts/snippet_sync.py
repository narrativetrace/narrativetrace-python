# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Rewrites drifted snippet blocks in place (`poe snippet-sync`; check logic in
`scripts/snippet_check.py`, wired into `poe check`).

English pages only, same as `translation_check.py`'s own split between staleness (checked) and
translated code-block content (never auto-rewritten) — a translated mirror's fix is a translator
restamping its header after this runs on the English source.

Also rewrites every NarrativeTrace install coordinate in every public document to this
repository's own version (`scripts/version_literals.py`), translated mirrors included, since a
coordinate is language-neutral and a mirror carrying a stale one would be just as unpasteable.
This is the ONLY writer of a coordinate — never hand-type one into a page.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.snippet_check import REPO_ROOT, sync_repository
from scripts.version_literals import read_version
from scripts.version_literals import sync as sync_version_literals


def main() -> int:
    changes = sync_repository(REPO_ROOT)
    changes.extend(sync_version_literals(REPO_ROOT, read_version(REPO_ROOT)))
    if not changes:
        print("snippet-sync: nothing to do — every embedded block already matches its source")
        return 0
    print("snippet-sync: resynced the following blocks from their source:")
    for change in changes:
        print(f"  {change}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
