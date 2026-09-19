# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Corpus replay for the five ``graphs.json`` rows added for the rendering rule (owner ruling
2026-09-17, "rendering reads state, never runs behaviour"; 2026-09-18 abstract-base refinement):
``record-accessor-with-counter``, ``platform-collection-side-effecting-iterator``,
``lookalike-collection-not-platform-defined``, ``abstract-map-subclass-override`` and
``abstract-collection-subclass-override``. Each row's expected outcome is "rendered without
executing" -- the renderer must never invoke the fixture's own overridden member. Mirrors Java's
``RenderingReadsStateCorpusReplayTest``.

INTENT: :mod:`test_value_renderer_redaction_properties` and
:mod:`test_capture_path_redaction_conformance` already replay every row in ``graphs.json``
generically (through ``hostile_graphs.build``) for containment and well-formedness -- those pass
for all five rows today (a raising override degrades to the typed failure marker, which leaks
nothing). What neither checks is whether the override ran at all, which is the property these
rows exist for.

Four of the five are LIVE today: a dataclass field is read directly (``dataclasses.fields()`` plus
plain ``getattr``), never through the shadowing property, so ``record-accessor-with-counter``
already holds; a type that is not ``isinstance`` of any of ``ValueRenderer``'s builtin collection
types (``list``/``tuple``/``set``/``frozenset``) falls through to ordinary field introspection,
never its own ``__iter__``, so ``lookalike-collection-not-platform-defined`` already holds too.
``abstract-map-subclass-override`` and ``abstract-collection-subclass-override`` are LIVE for the
same reason: ``_render_if_enumerable`` dispatches a map by ``isinstance(value, dict)`` and a
collection by ``isinstance(value, _COLLECTION_TYPES)`` (``list``/``tuple``/``set``/``frozenset``
exactly) -- neither check is true for a bare ``collections.abc.Mapping``/``Collection`` subclass,
so both fall straight through to plain object introspection of the subclass's own fields, never
calling ``items()``/``__iter__``. Unlike Java's ``AbstractMap``/``AbstractCollection`` bug (which
enumerated any subclass of those abstract bases unconditionally, regardless of origin), Python's
dispatch was already origin/exact-type-gated before this refinement, so there was no equivalent
gap to close here.

The remaining one is PENDING: ``ValueRenderer._render_collection_body`` does ``list(value)``,
which dispatches to a ``list`` SUBCLASS's overridden ``__iter__`` via the ``isinstance`` check (not
an exact-type or platform-ancestor-bound check) -- the same gap ``test_render_reads_state.py``'s
``TestHostileListSubclassIter`` already pins pending.

Two more rows landed on the master 2026-09-18 (pair #6 T) for the two gaps pair #5 I's report
left open: ``structured-path-user-collection-not-enumerated``
and ``fieldless-abstract-subclass-tostring-door``. Java marks both ``@Disabled`` in
``RenderingReadsStateCorpusReplayTest`` (pending -- pair #6 I has not closed either gap there yet).
Both are LIVE in this port already, each for a different, checked reason -- neither is a targeted
fix, both are pre-existing shape:

* ``structured-path-user-collection-not-enumerated`` reuses the ``lookalikeCollection`` member,
  replayed through ``render_structured`` instead of ``render``. Java's structured path enumerates
  any ``java.util.Collection`` unconditionally (origin-blind). This port's
  ``_render_structured_complex`` dispatches a collection by the exact same origin check the flat
  path already uses (``isinstance(value, _COLLECTION_TYPES)``, i.e. exactly
  ``list``/``tuple``/``set``/``frozenset``) -- a hand-rolled ``collections.abc.Collection`` is none
  of those, so it falls straight through to plain object introspection on the structured path too.
  There was never a second, separately-gated dispatch to fix.
* ``fieldless-abstract-subclass-tostring-door`` is Java's fieldless ``AbstractCollection``
  subclass, whose inherited ``toString()`` walks ``iterator()`` -- a door this port's
  ``collections.abc.Collection`` does not have: verified empirically (see
  ``hostile_graphs._FieldlessAbstractSubclassToStringDoor``'s docstring) that none of
  ``Container``/``Iterable``/``Sized``/``Collection`` overrides ``__str__``/``__repr__``, so a
  fieldless instance's default stringification is ``object``'s own inert
  ``<module.ClassName object at 0x...>``, never touching ``__iter__``. The door is now shut twice
  over: declaring no field reflection can read earns no trust at all here, so the value renders as
  its type name and no string conversion of its own -- inherited or not -- is called. The fixture
  carries no secret payload at all (mirrors Java's own note: the corpus factory's ``held`` local
  is unused on this arm), so there is no canary to assert absent for this row -- only the counter
  and the shape of the rendering.
"""

from __future__ import annotations

import pytest
from hostile_graphs import (
    SecretRecord,
    _AbstractCollectionSubclassOverride,
    _AbstractMapSubclassOverride,
    _CountingAccessor,
    _FieldlessAbstractSubclassToStringDoor,
    _LookalikeCollection,
    _SideEffectingIteratorList,
)
from oracles import contains_nowhere, sentinel_token

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.rendering import ValueRenderer
from narrativetrace.trace_object import trace_object

_PENDING = (
    "pending: the rendering rule: rendering reads state, never runs behaviour "
    "-- a list subclass's overridden __iter__ must be bypassed through the platform "
    "ancestor's own state, never invoked via isinstance dispatch"
)


class _FixtureParamService:
    """One traced method taking a single parameter -- the real capture path a corpus row's
    fixture is replayed through to prove rendering a hostile parameter opens no span of its own
    (mirrors ``test_render_reentrancy.py``'s ``HolderService``)."""

    def receive(self, value: object) -> None:
        return None


def _no_failure_marker(rendered: str, type_name: str) -> None:
    assert "<error:" not in rendered, f"render degraded to a typed failure marker: {rendered}"
    assert rendered != f"<{type_name}>", f"render degraded to the bare failure marker: {rendered}"


@pytest.fixture
def renderer() -> ValueRenderer:
    return ValueRenderer()


class TestRecordAccessorWithCounterRow:
    def test_renders_without_invoking_the_accessor(self, renderer: ValueRenderer) -> None:
        fixture = _CountingAccessor(SecretRecord("item", "sentinel"))

        renderer.render(fixture)

        assert fixture.calls[0] == 0, "the accessor must never run"


class TestPlatformCollectionSideEffectingIteratorRow:
    def test_renders_without_executing_the_override(self, renderer: ValueRenderer) -> None:
        # Observed RED today: `_render_collection_body` does `list(value)`, which dispatches to
        # the SUBCLASS's overridden `__iter__` (via `isinstance(value, _COLLECTION_TYPES)`, not an
        # exact-type or platform-ancestor-bound check) -- it raises, `iterator_calls` becomes 1,
        # and the whole collection degrades to the generic "<_SideEffectingIteratorList>" marker
        # instead of showing its element through `list`'s own backing state.
        fixture = _SideEffectingIteratorList(SecretRecord("item", "sentinel"))

        renderer.render(fixture)

        assert fixture.iterator_calls == 0, "the overridden __iter__ must never run"


class TestLookalikeCollectionRow:
    def test_renders_without_executing_its_own_iterator(self, renderer: ValueRenderer) -> None:
        fixture = _LookalikeCollection(SecretRecord("item", "sentinel"))

        renderer.render(fixture)

        assert fixture.iterator_calls == 0, "the hand-rolled __iter__ must never run"


class TestAbstractMapSubclassOverrideRow:
    def test_renders_without_executing_the_override(self, renderer: ValueRenderer) -> None:
        fixture = _AbstractMapSubclassOverride(SecretRecord("item", "sentinel"))

        renderer.render(fixture)

        assert fixture.items_calls == 0, "the overridden items() must never run"


class TestAbstractCollectionSubclassOverrideRow:
    def test_renders_without_executing_the_override(self, renderer: ValueRenderer) -> None:
        fixture = _AbstractCollectionSubclassOverride(SecretRecord("item", "sentinel"))

        renderer.render(fixture)

        assert fixture.iterator_calls == 0, "the overridden __iter__ must never run"


class TestStructuredPathUserCollectionNotEnumeratedRow:
    """``structured-path-user-collection-not-enumerated`` (master, 2026-09-18): reuses
    ``lookalikeCollection``, replayed through ``render_structured`` too -- LIVE, see the module
    docstring."""

    def test_renders_without_executing_its_own_iterator_on_either_path(
        self, renderer: ValueRenderer
    ) -> None:
        sentinel = sentinel_token()
        fixture = _LookalikeCollection(SecretRecord("item", sentinel))

        flat = renderer.render(fixture)
        assert fixture.iterator_calls == 0, "the flat path must never call the hand-rolled __iter__"
        contains_nowhere(sentinel, {"flat": flat})
        _no_failure_marker(flat, type(fixture).__name__)

        fixture.iterator_calls = 0
        structured = repr(renderer.render_structured(fixture))
        assert fixture.iterator_calls == 0, (
            "the structured path must never call the hand-rolled __iter__ either"
        )
        contains_nowhere(sentinel, {"structured": structured})
        _no_failure_marker(structured, type(fixture).__name__)

    def test_replayed_through_the_real_capture_path_opens_no_extra_span(self) -> None:
        sentinel = sentinel_token()
        fixture = _LookalikeCollection(SecretRecord("item", sentinel))
        ctx = ContextVarNarrativeContext()
        svc = trace_object(_FixtureParamService(), ctx)

        svc.receive(fixture)

        roots = ctx.capture_trace().roots
        assert [r.signature.method_name for r in roots] == ["receive"]
        assert roots[0].children == [], "rendering the parameter must never open a span of its own"
        assert fixture.iterator_calls == 0
        rendered_param = roots[0].signature.parameters[0].rendered_value
        contains_nowhere(sentinel, {"parameter": rendered_param})


class TestFieldlessAbstractSubclassToStringDoorRow:
    """``fieldless-abstract-subclass-tostring-door`` (master, 2026-09-18): LIVE for a reason that
    does not port from Java -- see the module docstring and
    ``hostile_graphs._FieldlessAbstractSubclassToStringDoor``'s. Carries no secret payload, so
    there is no canary to assert absent here -- only the counter and the shape of the
    rendering."""

    def test_renders_without_executing_the_override_on_either_path(
        self, renderer: ValueRenderer
    ) -> None:
        """The type-name rendering is the ANSWER here, not a degradation: a value declaring no
        field reflection can read is rendered by name, so neither the inherited string conversion
        nor the override behind it is ever reached. ``_no_failure_marker`` therefore does not
        apply to this row -- only the absence of a typed error marker does, and the counter."""
        _FieldlessAbstractSubclassToStringDoor.iterator_calls = 0
        fixture = _FieldlessAbstractSubclassToStringDoor()
        type_name = type(fixture).__name__

        flat = renderer.render(fixture)
        assert _FieldlessAbstractSubclassToStringDoor.iterator_calls == 0, (
            "the overridden __iter__ must never run, even reached through the inherited __str__"
        )
        assert flat == f"<{type_name}>", f"expected the type-name rendering, got: {flat}"

        _FieldlessAbstractSubclassToStringDoor.iterator_calls = 0
        structured = repr(renderer.render_structured(fixture))
        assert _FieldlessAbstractSubclassToStringDoor.iterator_calls == 0, (
            "the overridden __iter__ must never run on the structured path either"
        )
        assert "<error:" not in structured, f"structured render degraded to a marker: {structured}"
        assert f"<{type_name}>" in structured, f"structured channel disagrees: {structured}"

    def test_replayed_through_the_real_capture_path_opens_no_extra_span(self) -> None:
        _FieldlessAbstractSubclassToStringDoor.iterator_calls = 0
        fixture = _FieldlessAbstractSubclassToStringDoor()
        ctx = ContextVarNarrativeContext()
        svc = trace_object(_FixtureParamService(), ctx)

        svc.receive(fixture)

        roots = ctx.capture_trace().roots
        assert [r.signature.method_name for r in roots] == ["receive"]
        assert roots[0].children == [], "rendering the parameter must never open a span of its own"
        assert _FieldlessAbstractSubclassToStringDoor.iterator_calls == 0
