# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The release workflow publishes exactly the workspace's publishable packages.

`.github/workflows/publish.yml` keeps a hand-written `PUBLISHABLE_PACKAGES` list (a workflow
file cannot import `scripts/verify_publication_packages.py`), while the contract gate and
`poe verify-publication` derive the same set from the workspace itself. The two drifted once:
Phase 3 added `narrativetrace-skills` and `narrativetrace-tooling` (2026-09-26) and the
workflow kept listing eight names, so a release would have shipped without the carrier the
contract gate installs — red every night, by design, with nothing to publish it. This test is
the seam: the list in the workflow IS the derived set, or the build is red.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.verify_publication_packages import derive_workspace_packages

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"


def _workflow_publishable_packages() -> list[str]:
    """The names under `PUBLISHABLE_PACKAGES: >-`: every indented line until the block ends."""
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^  PUBLISHABLE_PACKAGES: >-\n((?:    \S+\n)+)", text, flags=re.MULTILINE)
    assert match is not None, "publish.yml has no PUBLISHABLE_PACKAGES folded block"
    return match.group(1).split()


def test_the_workflow_lists_exactly_the_publishable_workspace_packages() -> None:
    derived = sorted(p.name for p in derive_workspace_packages(REPO_ROOT) if p.publish)
    listed = _workflow_publishable_packages()
    assert len(listed) == len(set(listed)), f"duplicate names in publish.yml: {listed}"
    assert sorted(listed) == derived


def test_the_workflow_never_lists_a_private_package() -> None:
    private = {p.name for p in derive_workspace_packages(REPO_ROOT) if not p.publish}
    assert private, (
        "the workspace is expected to carry at least one Private :: Do Not Upload member"
    )
    assert private.isdisjoint(_workflow_publishable_packages())
