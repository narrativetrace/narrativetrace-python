# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for the version-literal lint's sync/check round trip.

The example-based cases beside this file (`test_version_literals.py`) pin the coordinate forms
this repository's documentation actually writes. These pin the invariant that holds for ANY
version the release ever carries: whatever the version source says, a synced page satisfies the
check, and syncing it again is a no-op — the two properties a "the build writes it, the gate
reads it" pair has to have, or a release bump leaves `poe check` red with no page to blame.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from scripts.version_literals import check, sync

_VERSIONS = st.builds(
    lambda major, minor, patch: f"{major}.{minor}.{patch}",
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
)

_PAGE = """# Guide

```bash
uv add narrativetrace=={pinned}
uv run --with narrativetrace-pytest=={pinned} pytest
```

`dependencies = ["narrativetrace>={pinned}"]`, and `structlog==25.1.0` belongs to someone else.
"""


def _documentation(root: Path, pinned: str) -> Path:
    page = root / "documentation" / "guide.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(_PAGE.format(pinned=pinned), encoding="utf-8")
    return page


@settings(max_examples=50, deadline=None)
@given(pinned=_VERSIONS, released=_VERSIONS)
def test_a_synced_page_always_satisfies_the_check(pinned: str, released: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _documentation(root, pinned)

        sync(root, released)

        assert check(root, released) == []


@settings(max_examples=50, deadline=None)
@given(pinned=_VERSIONS, released=_VERSIONS)
def test_syncing_a_synced_page_again_writes_nothing(pinned: str, released: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        page = _documentation(Path(directory), pinned)

        sync(Path(directory), released)
        settled = page.read_text(encoding="utf-8")

        assert sync(Path(directory), released) == []
        assert page.read_text(encoding="utf-8") == settled
