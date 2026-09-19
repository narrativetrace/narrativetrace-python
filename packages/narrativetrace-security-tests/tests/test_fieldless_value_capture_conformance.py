# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Drives values that carry NO state reflection can read through the REAL capture path.

**The shape under test.** The rendering rule allows rendering to run exactly two pieces of user
code: the narrative-summary hook, and a *stateless leaf*'s own string conversion. "Stateless" was
decided by counting instance fields -- an empty ``__dict__`` and no filled ``__slots__`` slot --
and that count is not a statement about what a value holds. A ``ctypes.Structure`` subclass keeps
its fields in C-level descriptors; an ordinary class can keep its state in a module-level table
keyed by identity, or in a closure. All three reflect as fieldless, all three can print every
field they hold from their own ``__repr__``, and that text reached the trace with nothing but a
length cap in front of it -- past redaction by field name, past the deny-list, past the caps that
apply to a walked composite. A field the policy denies was rendered whole, name and value
together, in both channels.

**The rule the assertions below pin.** Trust in a value's own text is granted by ORIGIN -- the
standard library's own value types -- never by "this value has no field I can see". Any other
fieldless value renders as its type name: present in the trace, bounded, and unread.

**Real capture path, not a shortcut.** Every case is driven through an actual
``trace_object``-wrapped method call whose parameter is named innocuously (``data``), so no name
axis can be credited with the outcome, and is asserted against the captured
``ParameterCapture.rendered_value`` and ``structured_value`` *and* every rendered artifact --
Markdown, indented text, prose, JSON export, canonical entries, chapter. Asserting on one channel
alone is how a leak survives in the other.
"""

from __future__ import annotations

import ctypes

import pytest

from narrativetrace.chapter import export_chapter
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.export import export, export_document
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import ParameterCapture
from narrativetrace.trace_object import trace_object
from narrativetrace.tree_canonical import export_canonical_entries

_METADATA = TraceMetadata("Fieldless value capture", ScenarioResult.SUCCESS)

_CSTRUCT_SECRET = "LEAK-TOKEN-cstruct-9f21"
_SIDE_TABLE_SECRET = "LEAK-TOKEN-side-table-4c07"


class CStructCredentials(ctypes.Structure):
    """Fields held as C-level descriptors: invisible to ``vars()``/``__slots__``, printed in full
    by the type's own text."""

    _fields_ = (("label", ctypes.c_char_p), ("secret", ctypes.c_char_p))

    def __repr__(self) -> str:
        return f"CStructCredentials(label={self.label.decode()}, secret={self.secret.decode()})"


_SIDE_TABLE: dict[int, str] = {}


class SideTableHolder:
    """The same shape with no C involved: the state lives in a module-level table keyed by
    identity, so reflection finds nothing while the type's own text prints everything."""

    __slots__ = ()

    def __init__(self, secret: str) -> None:
        _SIDE_TABLE[id(self)] = secret

    def __repr__(self) -> str:
        return f"SideTableHolder(secret={_SIDE_TABLE[id(self)]})"


class _ValueParamService:
    """One innocuous parameter name, so only the argument's own shape can decide the outcome."""

    def method(self, data: object) -> bool:
        return True


def _capture_and_render(argument: object) -> tuple[list[ParameterCapture], list[str]]:
    context = ContextVarNarrativeContext()
    trace_object(_ValueParamService(), context).method(argument)
    tree = context.capture_trace()
    params = list(tree.roots[0].signature.parameters)
    artifacts = [
        MarkdownRenderer().render_document(tree, _METADATA),
        IndentedTextRenderer().render(tree),
        ProseRenderer().render(tree),
        export(tree),
        export_document(tree, _METADATA),
        export_canonical_entries(tree),
        export_chapter(tree, _METADATA),
    ]
    return params, artifacts


_CASES = [
    pytest.param(
        CStructCredentials(b"prod-db", _CSTRUCT_SECRET.encode()),
        _CSTRUCT_SECRET,
        "CStructCredentials",
        id="c-struct-fields",
    ),
    pytest.param(
        SideTableHolder(_SIDE_TABLE_SECRET),
        _SIDE_TABLE_SECRET,
        "SideTableHolder",
        id="identity-keyed-side-table",
    ),
]


class TestFieldlessValueRendersAsItsTypeNameThroughTheCapturePath:
    @pytest.mark.parametrize(("value", "secret", "type_name"), _CASES)
    def test_the_secret_reaches_neither_channel_and_the_type_name_reaches_both(
        self, value: object, secret: str, type_name: str
    ) -> None:
        params, _ = _capture_and_render(value)

        leaked_text = [p.name for p in params if secret in p.rendered_value]
        leaked_structured = [p.name for p in params if secret in str(p.structured_value)]
        assert not leaked_text, f"secret reached the text channel for {leaked_text}"
        assert not leaked_structured, f"secret reached the structured channel {leaked_structured}"
        assert all(f"<{type_name}>" == p.rendered_value for p in params), (
            f"the value was not rendered as its type name: {[p.rendered_value for p in params]}"
        )
        assert all(f"<{type_name}>" in str(p.structured_value) for p in params), (
            f"structured channel disagrees: {[str(p.structured_value) for p in params]}"
        )

    @pytest.mark.parametrize(("value", "secret", "type_name"), _CASES)
    def test_the_secret_reaches_no_rendered_artifact(
        self, value: object, secret: str, type_name: str
    ) -> None:
        _, artifacts = _capture_and_render(value)

        leaked = [index for index, artifact in enumerate(artifacts) if secret in artifact]
        assert not leaked, f"secret reached rendered artifact(s) {leaked}"
        assert any(type_name in artifact for artifact in artifacts), (
            "the value vanished from every artifact -- it must stay visible as a type name"
        )
