# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Mechanical rename suggestions from a deprecated identifier to its canonical phrase.

``RenameSuggester``. INTENT: a vocabulary violation is actionable only if the fix is
obvious — this splices the canonical phrase's tokens into the identifier's own casing style
(``snake_case`` / ``camelCase`` / ``PascalCase``), so the suggestion reads as "the same kind of
name, different words" rather than a foreign spelling convention.

Casing is detected from the identifier being replaced, never from the canonical phrase (which
carries no casing at all — it is glossary-normalized, lowercase, space-separated). A single-token
identifier degrades to whichever style still applies (``PascalCase``/``camelCase`` capitalize their
one token; ``snake_case`` needs no separator either way).
"""

from __future__ import annotations

from enum import Enum, auto


class _Casing(Enum):
    SNAKE = auto()
    PASCAL = auto()
    CAMEL = auto()


def _detect_casing(identifier: str) -> _Casing:
    if "_" in identifier:
        return _Casing.SNAKE
    if identifier[:1].isupper():
        return _Casing.PASCAL
    return _Casing.CAMEL


def _render(tokens: list[str], casing: _Casing) -> str:
    if casing is _Casing.SNAKE:
        return "_".join(tokens)
    if casing is _Casing.PASCAL:
        return "".join(token.capitalize() for token in tokens)
    head, *rest = tokens
    return head + "".join(token.capitalize() for token in rest)


def suggest_rename(identifier: str, canonical_phrase: str) -> str:
    """Splices ``canonical_phrase`` into ``identifier``'s own casing style.

    Args:
        identifier: the deprecated spelling actually found in code (e.g.
            ``open_account_with_overdraft``).
        canonical_phrase: the glossary's normalized replacement (e.g. ``"open overdraft
            account"`` — lowercase, space-separated).

    Returns:
        A suggested identifier in the same casing style as ``identifier``, spelling
        ``canonical_phrase``'s tokens instead (``open_overdraft_account``).

    Raises:
        ValueError: if either argument is blank.
    """
    if not identifier.strip():
        raise ValueError("identifier must not be blank")
    if not canonical_phrase.strip():
        raise ValueError("canonical_phrase must not be blank")
    tokens = canonical_phrase.split(" ")
    suggestion = _render(tokens, _detect_casing(identifier))
    assert suggestion, "a rename suggestion must never be empty"
    return suggestion
