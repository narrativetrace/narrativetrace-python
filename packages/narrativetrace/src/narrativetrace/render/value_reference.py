# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Content-addressed deduplication of captured values for one rendering pass.

``ValueReferenceIndex`` (``ai.narrativetrace.core.render``). A value whose rendered
form repeats across a trace carries information only where it differs; byte-identical repetition
is noise that hides the render that changed. This index collects the rendered parameter and
return values of a :class:`~narrativetrace.tree.TraceTree`, decides which of them earn a
reference (long enough and emitted more than once), and hands renderers a display form: the first
emission defines ``‹label›=full``, later emissions are just ``‹label›``. Equality is byte
equality of the rendered string.

A value that differs is not simply re-rendered in full, though. When two rendered forms belong to
the same *entity* — same structured type name, same value in the identity field that names the
label — the later one renders as ``‹label›′{amount: 100.0→92.0}``, a diff against the reference
this document already defines (see :mod:`narrativetrace.render.value_delta`). Anything the diff
cannot express falls back to the full render, unchanged.

One instance serves exactly one rendering pass: label definition order follows emission order, so
the instance is stateful and must not be shared across renders.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.redaction import REDACTED_MARKER
from narrativetrace.render.value_delta import value_delta
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk
from narrativetrace.values import ObjectVal, RenderedValue, StringVal

_MIN_REF_LENGTH = 40
_MAX_LABEL_LENGTH = 24
_IDENTITY_FIELDS = ("name", "id", "description", "title", "key", "label", "code")


def _identity_field_of(obj: ObjectVal) -> tuple[str, str] | None:
    """The first identity-signalling field with a usable plain string, as its name and text."""
    for field_name in _IDENTITY_FIELDS:
        field = obj.fields.get(field_name)
        if isinstance(field, StringVal) and field.value.strip() and field.value != REDACTED_MARKER:
            return field_name, field.value
    return None


def _cap_label(text: str) -> str:
    return f"{text[:_MAX_LABEL_LENGTH]}…" if len(text) > _MAX_LABEL_LENGTH else text


def _base_label(structured: RenderedValue | None) -> str | None:
    """Label stem for a value: its identity field, else its type name, else ``None``."""
    if not isinstance(structured, ObjectVal):
        return None
    identity = _identity_field_of(structured)
    return _cap_label(control_sanitize(identity[1])) if identity else structured.type_name


def _identity_key(structured: RenderedValue | None) -> str | None:
    """Stable key for "the same entity": type name plus the uncapped identity-field value.

    Two captures sharing this key are the same thing at two moments, which is what makes a delta
    between them meaningful. ``None`` when the value carries no identity field — a type name alone
    would group unrelated instances of the same class, and a diff between two different expenses
    is noise, not signal.
    """
    if not isinstance(structured, ObjectVal):
        return None
    identity = _identity_field_of(structured)
    return f"{structured.type_name} {identity[0]} {identity[1]}" if identity else None


def _occurrences_in(container: str, value: str) -> int:
    occurrences = 0
    idx = container.find(value)
    while idx >= 0:
        occurrences += 1
        idx = container.find(value, idx + len(value))
    return occurrences


def _containment_count(value: str, counts: dict[str, int]) -> int:
    """Emissions of ``value`` nested inside other captured values, weighted by their counts."""
    return sum(
        _occurrences_in(container, value) * count
        for container, count in counts.items()
        if container != value
    )


def _count_value(
    rendered: str | None,
    structured: RenderedValue | None,
    counts: dict[str, int],
    structured_by_content: dict[str, RenderedValue],
) -> None:
    if rendered is None or len(rendered) < _MIN_REF_LENGTH:
        return
    counts[rendered] = counts.get(rendered, 0) + 1
    if structured is not None:
        structured_by_content.setdefault(rendered, structured)


def _count_node(
    node: TraceNode,
    counts: dict[str, int],
    structured_by_content: dict[str, RenderedValue],
    walk: TreeWalk | None = None,
) -> None:
    walk = walk if walk is not None else TreeWalk()
    for param in node.signature.parameters:
        if not param.redacted:
            _count_value(
                param.rendered_value, param.structured_value, counts, structured_by_content
            )
    if isinstance(node.outcome, Returned):
        _count_value(
            node.outcome.rendered_value,
            node.outcome.structured_value,
            counts,
            structured_by_content,
        )
    if walk.stop_reason(node) is None:
        walk.enter(node)
        try:
            for child in node.children:
                _count_node(child, counts, structured_by_content, walk)
        finally:
            walk.exit(node)


def _any_pair_diffs(values: list[RenderedValue]) -> bool:
    """Whether any two of one identity's rendered forms differ by scalar fields alone."""
    return any(value_delta(one, other) is not None for one in values for other in values)


def _forms_by_identity(structured_by_content: dict[str, RenderedValue]) -> dict[str, list[str]]:
    forms: dict[str, list[str]] = {}
    for rendered, value in structured_by_content.items():
        key = _identity_key(value)
        if key is not None:
            forms.setdefault(key, []).append(rendered)
    return forms


def _delta_keys(structured_by_content: dict[str, RenderedValue]) -> dict[str, str]:
    """Maps each candidate value to its identity key, when that identity is worth diffing.

    A key qualifies when it covers more than one rendered form — the same entity, captured again
    with something changed — *and* at least one of those forms can actually be expressed as a
    delta of another. The second condition keeps the fallback silent: a pair whose difference is
    structural renders exactly as it did before this feature existed, with no reference label
    stamped on a definition nothing ever refers back to.
    """
    key_by_content: dict[str, str] = {}
    for key, forms in _forms_by_identity(structured_by_content).items():
        if _any_pair_diffs([structured_by_content[f] for f in forms]):
            for rendered in forms:
                key_by_content[rendered] = key
    return key_by_content


class ValueReferenceIndex:
    """Per-render index deciding how each captured value is emitted."""

    __slots__ = (
        "_base_label_uses",
        "_defined_labels",
        "_delta_key_by_content",
        "_generic_counter",
        "_group_anchors",
        "_referenced",
        "_referenced_by_length_desc",
        "_structured_by_content",
    )

    def __init__(
        self, referenced: set[str], structured_by_content: dict[str, RenderedValue]
    ) -> None:
        self._referenced = referenced
        self._referenced_by_length_desc = sorted(referenced, key=lambda s: (-len(s), s))
        self._structured_by_content = structured_by_content
        self._delta_key_by_content = _delta_keys(structured_by_content)
        self._group_anchors: dict[str, str] = {}
        self._defined_labels: dict[str, str] = {}
        self._base_label_uses: dict[str, int] = {}
        self._generic_counter = 0

    @staticmethod
    def build(tree: TraceTree) -> ValueReferenceIndex:
        """Collects candidates from the tree; values emitted at least twice earn a reference."""
        counts: dict[str, int] = {}
        structured_by_content: dict[str, RenderedValue] = {}
        for root in tree.roots:
            _count_node(root, counts, structured_by_content)
        referenced = {
            value
            for value, count in counts.items()
            if count + _containment_count(value, counts) >= 2
        }
        return ValueReferenceIndex(referenced, structured_by_content)

    def display(self, rendered: str | None) -> str | None:
        """The emission form of a rendered value.

        Full text for an unreferenced value, ``‹label›=full`` the first time a referenced value is
        emitted, ``‹label›`` afterwards, and ``‹label›′{field: before→after}`` for a later emission
        of the same entity that changed.
        """
        if rendered is None:
            return None
        if rendered in self._referenced:
            return self._reference_display(rendered)
        return self._delta_display(rendered) or self._replace_contained(rendered)

    def _reference_display(self, value: str) -> str:
        """Defines or reuses a byte-repeated value's label.

        A repeated value that is itself a changed re-capture of an already-defined reference is
        defined AS the delta (``‹label·2›=‹label›′{…}``) rather than as a second full blob.
        """
        existing = self._defined_labels.get(value)
        if existing is not None:
            return existing
        created = self._new_label(value)
        self._defined_labels[value] = created
        as_delta = self._delta_against_anchor(value)
        self._remember_anchor(value)
        return f"{created}={as_delta or self._replace_contained(value)}"

    def _delta_display(self, rendered: str) -> str | None:
        """Emission form for a value whose identity was seen in more than one rendered form."""
        key = self._delta_key_by_content.get(rendered)
        if key is None:
            return None
        if key in self._group_anchors:
            return self._delta_against_anchor(rendered)
        label = self._new_label(rendered)
        self._defined_labels[rendered] = label
        self._group_anchors[key] = rendered
        return f"{label}={self._replace_contained(rendered)}"

    def _remember_anchor(self, rendered: str) -> None:
        """Records a newly-labelled value as its identity's reference, if it is part of a pair."""
        key = self._delta_key_by_content.get(rendered)
        if key is not None:
            self._group_anchors.setdefault(key, rendered)

    def _delta_against_anchor(self, rendered: str) -> str | None:
        """``‹anchor›′{field: before→after}`` when this identity already has a defined reference."""
        key = self._delta_key_by_content.get(rendered)
        anchor = self._group_anchors.get(key) if key is not None else None
        if anchor is None:
            return None
        delta = value_delta(
            self._structured_by_content.get(anchor), self._structured_by_content.get(rendered)
        )
        return None if delta is None else f"{self._defined_labels[anchor]}′{delta}"

    def _replace_contained(self, rendered: str) -> str:
        """Replaces referenced values nested inside ``rendered``, longest first."""
        result = rendered
        for value in self._referenced_by_length_desc:
            if value != rendered:
                result = self._replace_occurrences(result, value)
        return result

    def _replace_occurrences(self, text: str, value: str) -> str:
        idx = text.find(value)
        if idx < 0:
            return text
        out: list[str] = []
        start = 0
        while idx >= 0:
            out.append(text[start:idx])
            out.append(self._reference_display(value))
            start = idx + len(value)
            idx = text.find(value, start)
        out.append(text[start:])
        return "".join(out)

    def _new_label(self, rendered: str) -> str:
        base = _base_label(self._structured_by_content.get(rendered))
        if base is None:
            self._generic_counter += 1
            return f"‹v{self._generic_counter}›"
        uses = self._base_label_uses.get(base, 0) + 1
        self._base_label_uses[base] = uses
        return f"‹{base}›" if uses == 1 else f"‹{base}·{uses}›"
