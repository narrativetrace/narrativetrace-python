# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Turns a declarative hostile-corpus redaction ``kind`` row (``redaction.json``) into a live
composite object -- the redaction-corpus counterpart to ``hostile_graphs.py``'s builder for
``graphs.json``'s ``kind`` shapes, added 2026-09-11 for the family-wide fix that stopped trusting
a composite's native ``__str__``/summary (see ``rendering.py``'s module docstring and
``documentation/security-testing.md``).

Four kinds, one live shape apiece -- the exact defects the fix closes:

* ``curatedToString`` -- a composite carrying a deny-listed field, interpolated directly by a
  hand-written ``__str__``. Before the fix, ``ValueRenderer`` trusted this ``__str__`` outright
  (only a type with NO custom ``__str__`` was introspected) and the field-name redaction check
  never ran.
* ``curatedToStringNested`` -- a composite with no sensitive field of its own, whose ``__str__``
  interpolates a NESTED composite that does carry one: ordinary f-string formatting calls
  ``str()`` on the nested object too, so the leak survives one container deep, the same bug class
  a wrapper toString() leak always is.
* ``mapKey`` -- the same curated-``__str__`` shape again, planted as a dict KEY rather than a
  value: before the fix a map entry's key was always a bare, unmediated ``str(key)``, so a
  sensitive key leaked unconditionally regardless of what its value held.
* ``throwingSummary`` -- a composite whose ``@narrative_summary`` method raises, with the secret
  folded into the EXCEPTION MESSAGE (never the field name). A fix that renders ``str(exc)``
  instead of the exception's own type name would still leak it; a fix that merely swapped the
  post-failure fallback path (introspection) would leak it too, since the secret sits under a
  field name the deny-list does not recognise -- only the typed ``<error: TypeName>`` marker,
  never falling through to any other rendering of the object, closes this one.
"""

from __future__ import annotations

from collections.abc import Callable

from narrativetrace.markers import narrative_summary


class _CuratedStrTopLevel:
    """``curatedToString``: a deny-listed field, interpolated by a hand-written ``__str__``."""

    def __init__(self, password: str) -> None:
        self.password = password

    def __str__(self) -> str:
        return f"CuratedStrTopLevel(password={self.password})"


class _CuratedStrNestedInner:
    """The nested composite that actually carries the sensitive field."""

    def __init__(self, password: str) -> None:
        self.password = password

    def __str__(self) -> str:
        return f"Inner(password={self.password})"


class _CuratedStrNestedOuter:
    """``curatedToStringNested``: no sensitive field itself; its ``__str__`` interpolates
    ``detail``, whose own ``__str__`` is what actually carries the secret."""

    def __init__(self, detail: _CuratedStrNestedInner) -> None:
        self.detail = detail

    def __str__(self) -> str:
        return f"Outer(detail={self.detail})"


class _SensitiveMapKey:
    """``mapKey``: the curated-``__str__`` shape again, planted as a dict KEY."""

    def __init__(self, password: str) -> None:
        self.password = password

    def __str__(self) -> str:
        return f"KeyHolder(password={self.password})"


class _ThrowingSummary:
    """``throwingSummary``: the summary raises with the secret in the exception MESSAGE, under a
    field name (``payload``) the deny-list does not recognise -- so only the typed error marker,
    never a fallback rendering of the object, keeps it from leaking."""

    def __init__(self, payload: str) -> None:
        self.payload = payload

    @narrative_summary
    def summary(self) -> str:
        raise RuntimeError(f"summary failed for {self.payload}")


def _nested(secret: str) -> _CuratedStrNestedOuter:
    return _CuratedStrNestedOuter(_CuratedStrNestedInner(secret))


_KIND_BUILDERS: dict[str, Callable[[str], object]] = {
    "curatedToString": _CuratedStrTopLevel,
    "curatedToStringNested": _nested,
    "mapKey": lambda secret: {_SensitiveMapKey(secret): "value"},
    "throwingSummary": _ThrowingSummary,
}


def build(kind: str, secret: str) -> object:
    """Builds the live composite ``kind`` declares, planting ``secret`` in it.

    Takes ``kind`` as a plain string (a :class:`~hostile_corpus.RedactionCase`'s own ``kind``
    field) rather than the case itself, so this module never needs to import ``hostile_corpus`` --
    ``hostile_corpus.RedactionCase.payload`` imports this module's :func:`build`, and a
    module-level import back would be circular.
    """
    return _KIND_BUILDERS[kind](secret)
