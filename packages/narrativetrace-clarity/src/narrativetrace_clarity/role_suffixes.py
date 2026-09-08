# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Dictionary of recognized class-name suffixes (Service, Repository, Factory, ...).

``RoleSuffixDictionary``. Suffix sets and the expected-verb map are byte-identical to
the Java source (see ``_role_suffixes_data``).
"""

from __future__ import annotations

from enum import Enum

from narrativetrace_clarity import _role_suffixes_data as _data


class Category(Enum):
    """Role-suffix categories."""

    DESIGN_PATTERN = "DESIGN_PATTERN"
    FUNCTIONAL = "FUNCTIONAL"
    GENERIC = "GENERIC"
    UNKNOWN = "UNKNOWN"


_DESIGN_PATTERN_SUFFIXES = frozenset(_data.DESIGN_PATTERN_SUFFIXES)
_FUNCTIONAL_SUFFIXES = frozenset(_data.FUNCTIONAL_SUFFIXES)
_GENERIC_SUFFIXES = frozenset(_data.GENERIC_SUFFIXES)
_EXPECTED_VERBS: dict[str, tuple[str, ...]] = dict(_data.EXPECTED_VERBS)

assert len(_DESIGN_PATTERN_SUFFIXES) == 15
assert len(_FUNCTIONAL_SUFFIXES) == 50
assert len(_GENERIC_SUFFIXES) == 13


def classify(suffix: str) -> tuple[Category, float]:
    """Returns the (category, score) for a class-name suffix token."""
    lower = suffix.lower()
    if lower in _DESIGN_PATTERN_SUFFIXES:
        return Category.DESIGN_PATTERN, 1.0
    if lower in _FUNCTIONAL_SUFFIXES:
        return Category.FUNCTIONAL, 1.0
    if lower in _GENERIC_SUFFIXES:
        return Category.GENERIC, 0.3
    return Category.UNKNOWN, 0.6


def expected_verbs(suffix: str) -> tuple[str, ...]:
    """Returns the ordered verbs expected of methods on a class with this suffix (or empty)."""
    return _EXPECTED_VERBS.get(suffix.lower(), ())
