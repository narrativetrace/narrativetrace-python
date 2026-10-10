# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Every Tier B case the framework table names exists, replays the published init prompt, and
installs from the checkout — the table is newer than the release a trial would otherwise grade."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from narrativetrace_tooling.frameworks.table import NO_TIER_B_CASE, ROWS

_CASES = Path(__file__).resolve().parents[1] / "evals" / "add-narrative-tracing"
_NAMED = [row for row in ROWS if row.tier_b_case != NO_TIER_B_CASE]


def test_the_table_names_at_least_one_case() -> None:
    assert [row.id for row in _NAMED] == ["asgi"]


@pytest.mark.parametrize("row", _NAMED, ids=lambda row: row.id)
def test_the_named_case_replays_the_published_prompt_from_the_checkout(row) -> None:  # type: ignore[no-untyped-def]
    case = _CASES / row.tier_b_case
    published = (_CASES / "init-prompt-existing-project" / "prompt.md").read_bytes()

    assert (case / "prompt.md").read_bytes() == published
    assert json.loads((case / "case.json").read_text(encoding="utf-8"))["install"] == "checkout"
    assert (case / "graders" / "verify.sh").is_file()
