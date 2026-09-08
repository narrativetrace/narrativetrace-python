# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Translation coverage/review dashboard (`poe translation-status`, not wired into `poe check`).

Human dashboard only — the same report every runtime prints. Publish-gating
on the review field is a later owner decision this platform does not make (see
`scripts/translation_check.py`'s `review_summary_line`).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run directly (`python scripts/translation_status.py`), Python puts this file's own directory —
# not the repository root — on sys.path[0], so the package-qualified import below needs the root
# added explicitly. Pytest's rootdir insertion already provides this when the module is imported
# from a test instead.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.translation_check import REPO_ROOT, load_manifest_or_none, status_report


def main() -> int:
    print(status_report(REPO_ROOT, load_manifest_or_none(REPO_ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
