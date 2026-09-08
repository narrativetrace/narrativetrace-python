# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Maps domain nouns to their preferred verb collocations for naming suggestions.

``CollocationDictionary``. The map is the union (per noun) of 35 domain category maps,
byte-identical to the Java source (see ``_collocations_data``).
"""

from __future__ import annotations

from narrativetrace_clarity import _collocations_data as _data

_COLLOCATIONS: dict[str, frozenset[str]] = {
    noun: frozenset(verbs) for noun, verbs in _data.COLLOCATIONS.items()
}


def preferred_verbs(noun: str) -> frozenset[str]:
    """Returns the preferred verbs for a noun, or an empty set."""
    if not noun or not noun.strip():
        return frozenset()
    return _COLLOCATIONS.get(noun.lower(), frozenset())


def is_preferred(verb: str, noun: str) -> bool:
    """Whether ``verb`` is a preferred collocation for ``noun``."""
    if not verb or not verb.strip():
        return False
    return verb.lower() in preferred_verbs(noun)
