# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The containment oracle counts a heading however it is written."""

from __future__ import annotations

import pytest
from formats import heading_count


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("# h\n\nbody", 1),
        ("text\n===", 1),
        ("text\n---", 1),
        ("text\n--", 1),
        ("text\n   ===  ", 1),
        ("text\n\n---", 0),
        ("text\n    ---", 0),
        ("text\n\\---", 0),
        ("a - b\nx == y", 0),
        ("| a |\n|---|", 0),
    ],
)
def test_a_setext_or_atx_heading_is_counted_and_prose_is_not(markdown: str, expected: int) -> None:
    assert heading_count(markdown) == expected
