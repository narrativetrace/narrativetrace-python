# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Converts display names into human-readable scenario titles.

``ScenarioFramer``. Strips a trailing ``(...)`` parameter list, passes spaced names
through unchanged, and otherwise humanises snake/camel names with a capitalised first letter.
"""

from __future__ import annotations

import re

_TRAILING_PARENS = re.compile(r"\([^)]*\)$")
_CAMEL_BOUNDARY = re.compile(r"([a-z])([A-Z])")


def humanize(display_name: str) -> str:
    """Humanises a display name into a readable title fragment."""
    name = _TRAILING_PARENS.sub("", display_name)
    if not name:
        return ""
    if " " in name:
        return name
    words = _CAMEL_BOUNDARY.sub(r"\1 \2", name.replace("_", " ")).lower()
    return words[0].upper() + words[1:]


def frame(display_name: str) -> str:
    """Returns ``"Scenario: " + humanize(display_name)``."""
    return "Scenario: " + humanize(display_name)
