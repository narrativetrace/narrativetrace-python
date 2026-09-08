# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Field-level difference between two structured renderings of the same entity.

``ValueDelta`` (``ai.narrativetrace.core.render``). When a captured value reappears
inside one trace slightly changed — the multi-currency case: a ledger returns an expense at
``100.00 USD``, the calculator receives it normalized to ``92.00 EUR`` — a second full render
hides the one field that moved inside a ~300-character blob. This composes the compact form
``{amount: 100.0→92.0, currency: "USD"→"EUR"}`` that
:class:`~narrativetrace.render.value_reference.ValueReferenceIndex` appends to the reference
label, so the change prints AS a diff.

The delta is computed from the two *structured* trees and formats only scalar leaves. It never
reconstructs a flat render from a structured value: the flat and structured channels are captured
independently (``ValueRenderer.render`` / ``render_structured``) and deriving one from the other
is a divergence class the Java runtime has already paid for twice. Any difference
that is not a scalar-to-scalar field change therefore yields ``None``, and the caller falls back
to the full flat render.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize
from narrativetrace.values import (
    BoolVal,
    FloatVal,
    InstantVal,
    IntVal,
    NullVal,
    ObjectVal,
    RenderedValue,
    StringVal,
)

_MAX_SCALAR_LENGTH = 60


def _cap(text: str) -> str:
    return f"{text[:_MAX_SCALAR_LENGTH]}…" if len(text) > _MAX_SCALAR_LENGTH else text


def _bare_scalar(value: RenderedValue) -> str | None:
    """The unquoted scalars. ``None`` for a nested object or list, which has no one-line form."""
    if isinstance(value, BoolVal):
        return "true" if value.value else "false"
    if isinstance(value, IntVal):
        return str(value.value)
    if isinstance(value, FloatVal):
        return str(value.value)
    if isinstance(value, InstantVal):
        return str(value.epoch_millis)
    return "null" if isinstance(value, NullVal) else None


def _scalar(value: RenderedValue) -> str | None:
    """Formats a scalar leaf the way the flat renderer prints it — strings quoted and escaped."""
    if isinstance(value, StringVal):
        return f'"{_cap(control_sanitize(value.value))}"'
    return _bare_scalar(value)


def _scalar_change(before: RenderedValue, after: RenderedValue) -> str | None:
    from_text = _scalar(before)
    to_text = _scalar(after)
    return None if from_text is None or to_text is None else f"{from_text}→{to_text}"


def _changed_fields(from_val: ObjectVal, to_val: ObjectVal) -> list[str] | None:
    """The ``field: before→after`` parts, or ``None`` once a changed field is itself structured."""
    parts: list[str] = []
    for name, before in from_val.fields.items():
        after = to_val.fields[name]
        if before == after:
            continue
        change = _scalar_change(before, after)
        if change is None:
            return None
        parts.append(f"{name}: {change}")
    return parts


def value_delta(reference: RenderedValue | None, changed: RenderedValue | None) -> str | None:
    """Composes the delta of ``changed`` against ``reference``.

    Returns ``None`` when the pair cannot be expressed as a scalar field diff — a different type,
    a different field set, no difference at all, or a changed field that is itself structured.
    """
    if not isinstance(reference, ObjectVal) or not isinstance(changed, ObjectVal):
        return None
    if reference.type_name != changed.type_name:
        return None
    if reference.fields.keys() != changed.fields.keys():
        return None
    parts = _changed_fields(reference, changed)
    return None if not parts else "{" + ", ".join(parts) + "}"


__all__ = ["value_delta"]
