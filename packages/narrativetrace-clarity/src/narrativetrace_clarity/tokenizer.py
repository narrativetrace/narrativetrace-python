# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tokenizes camelCase/PascalCase/snake_case identifiers into lowercase word lists.

``IdentifierTokenizer``. Splits on case transitions, letter/digit boundaries, and
underscores, then lowercases and drops empties.
"""

from __future__ import annotations

import re

_SPLIT_PATTERN = re.compile(
    r"(?<=[a-z])(?=[A-Z])"
    r"|(?<=[A-Z])(?=[A-Z][a-z])"
    r"|(?<=[a-zA-Z])(?=[0-9])"
    r"|(?<=[0-9])(?=[a-zA-Z])"
    r"|_"
)


def tokenize(identifier: str) -> list[str]:
    """Splits an identifier into lowercase word tokens."""
    return [part.lower() for part in _SPLIT_PATTERN.split(identifier) if part]
