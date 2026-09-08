# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Humanises identifier names for prose rendering.

``CamelCaseSplitter``. Python divergence: identifiers are usually ``snake_case``, so
:func:`to_phrase` humanises both ``camelCase`` (Java behaviour) *and* ``snake_case`` — e.g.
``OrderService`` and ``order_service`` both become ``order service``.
"""

from __future__ import annotations

import re

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")


def split(name: str) -> list[str]:
    """Splits ``name`` at lowercase→uppercase camelCase boundaries."""
    return _CAMEL_BOUNDARY.split(name)


def to_phrase(name: str) -> str:
    """Lower-cased, space-separated humanisation of a camelCase or snake_case identifier."""
    spaced = _CAMEL_BOUNDARY.sub(" ", name).replace("_", " ")
    return " ".join(spaced.split()).lower()
