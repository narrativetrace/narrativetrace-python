# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pending tests for the rendering rule (owner ruling 2026-09-17, every runtime).

Rendering reads a value's STATE by reflection/introspection and never runs the value's own
BEHAVIOUR: no accessor/getter, no computed property, no ``__str__``/``__repr__`` of a composite,
no ``__eq__``/``__hash__`` through collections, no ``__lt__`` through sorting. The only user code
rendering may execute is the two documented hooks (``@narrative_summary``, and the own ``__str__``
of a value whose ORIGIN earns it one -- never a value's merely for declaring no field) and only
under the rendering guard. Collections are enumerated only when the type is
EXACTLY a builtin (``type(v) in (list, tuple, dict, set, frozenset)``, never ``isinstance`` —
today's code uses ``isinstance``, which is exactly what the hostile-subclass tests below pin as
pending). A user subclass of a platform collection is enumerated through the platform ancestor's
own state (``list.__iter__``/``dict.items`` bound on the base type, bypassing the override); a
user type wrapping a platform collection in a field renders as an object whose field renders as
that collection. A third hook, ``__narrative_elements__`` (no production support today — every
fixture below that defines it is a TEST-SCOPE STUB that stays inert until ``rendering.py``
implements it), lets a type declare its elements safe to enumerate, under the guard, capped and
totality-guarded like every other element walk. An undeclared iterable renders as its type name
plus size, never its elements.

Each ``@pytest.mark.xfail(strict=True, ...)`` below is RED against today's code — see the
docstring/comment on each test for the observed failure — and flips to a real (unmarked) failure
the day the behaviour lands without anyone removing the marker. A test with no marker already
passes today and stays as a plain regression guard against ever weakening it.

Distinct from ``TestNativeStringificationNeverTrustedForComposites`` in ``test_rendering.py``
(composite ``__str__``/summary-hook coverage, already landed) and from
``test_render_reentrancy.py`` (the ``@narrative_summary``/stateless-leaf-``__str__`` reentrancy
guard, already landed) — this file covers the sites those two do not: property/getattr reads,
hostile builtin-collection subclasses, the undeclared/``Sequence``/``__narrative_elements__``
enumeration questions, the narration template resolver, and ``__repr__``/``__eq__``/``__hash__``/
``__lt__`` spies (no existing test spies on those four specifically).
"""

from __future__ import annotations

import collections.abc
import ctypes
import dataclasses
import datetime
import decimal
import pathlib
import uuid
from collections.abc import Iterator
from typing import NoReturn

import pytest

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.rendering import ValueRenderer
from narrativetrace.template import resolve
from narrativetrace.trace_object import trace_object
from narrativetrace.values import StringVal


@pytest.fixture
def renderer() -> ValueRenderer:
    return ValueRenderer()


_PENDING = "pending: rendering reads state, never runs behaviour — see CLAUDE.md"


# --------------------------------------------------------------------------- #
# 1. A dataclass property is never read by field introspection (LIVE today).  #
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class OrderWithComputedProperty:
    id: str
    quantity: int

    def __post_init__(self) -> None:
        # Not a dataclass field (no annotation) -- invisible to `dataclasses.fields()`, which is
        # exactly what `_field_names` uses for a dataclass. Kept off the instance dict shape the
        # renderer walks so this counter can prove whether `total` was ever read.
        self._total_reads = 0

    @property
    def total(self) -> int:
        self._total_reads += 1
        return self.quantity * 2


class TestDataclassPropertyNeverInvoked:
    def test_a_dataclass_propertys_counter_stays_zero_and_its_declared_fields_still_render(
        self, renderer: ValueRenderer
    ) -> None:
        order = OrderWithComputedProperty("ord-1", 3)

        rendered = renderer.render(order)

        assert order._total_reads == 0
        assert rendered == 'OrderWithComputedProperty(id="ord-1", quantity=3)'


# --------------------------------------------------------------------------- #
# 2. A hostile __getattr__/property never fires; real fields still render     #
#    (LIVE today).                                                            #
# --------------------------------------------------------------------------- #
class WithHostileGetattrAndProperty:
    def __init__(self) -> None:
        self.name = "widget"
        self.sku = "A1"

    def __getattr__(self, name: str) -> object:
        raise RuntimeError(f"no such attribute: {name}")

    @property
    def computed(self) -> str:
        raise RuntimeError("computed boom")


class TestHostileGetattrAndPropertyNeverFire:
    def test_real_fields_render_and_no_failure_marker_appears(
        self, renderer: ValueRenderer
    ) -> None:
        obj = WithHostileGetattrAndProperty()

        rendered = renderer.render(obj)

        assert 'name="widget"' in rendered
        assert 'sku="A1"' in rendered
        assert "<error" not in rendered
        assert "computed" not in rendered


# --------------------------------------------------------------------------- #
# 3. A list subclass whose __iter__ raises -- elements should render from the #
#    base list's own state, __iter__ never called. PENDING (isinstance, not   #
#    exact-type, admits the override -- rendering.py:305).                    #
# --------------------------------------------------------------------------- #
class HostileList(list[int]):
    def __init__(self, items: list[int]) -> None:
        super().__init__(items)
        self.iter_calls = 0

    def __iter__(self) -> Iterator[int]:
        self.iter_calls += 1
        raise RuntimeError("hostile iter")


class TestHostileListSubclassIter:
    def test_elements_render_from_base_list_state_and_the_overridden_iter_is_never_called(
        self, renderer: ValueRenderer
    ) -> None:
        # Observed RED today: `_render_collection_body` does `list(value)`, which dispatches to
        # the SUBCLASS's overridden `__iter__` (via `isinstance(value, _COLLECTION_TYPES)`, not an
        # exact-type check) -- it raises, `iter_calls` becomes 1, and the whole collection
        # degrades to the generic "<HostileList>" marker instead of showing its elements.
        hostile = HostileList([1, 2, 3])

        rendered = renderer.render(hostile)

        assert hostile.iter_calls == 0
        assert rendered == "[1, 2, 3]"


# --------------------------------------------------------------------------- #
# 4. A dict subclass whose items()/keys() raise -- entries should still       #
#    render. PENDING (same isinstance gap, rendering.py:307/343).             #
# --------------------------------------------------------------------------- #
class HostileDict(dict[str, int]):
    def __init__(self, **kwargs: int) -> None:
        super().__init__(**kwargs)
        self.items_calls = 0

    def items(self) -> NoReturn:
        self.items_calls += 1
        raise RuntimeError("hostile items")


class TestHostileDictSubclassItems:
    def test_entries_render_from_base_dict_state_and_the_overridden_items_is_never_called(
        self, renderer: ValueRenderer
    ) -> None:
        # Observed RED today: `_render_map_body` calls `value.items()`, dispatching to the
        # SUBCLASS's override -- it raises, `items_calls` becomes 1, and the map degrades to
        # "<HostileDict>" instead of its entries.
        hostile = HostileDict(a=1)

        rendered = renderer.render(hostile)

        assert hostile.items_calls == 0
        assert rendered == '{"a"=1}'


# --------------------------------------------------------------------------- #
# 5. A Sequence implementation delegating to a private list renders as an     #
#    object whose field renders as that collection (LIVE today).             #
# --------------------------------------------------------------------------- #
class WrappedSequence(collections.abc.Sequence[int]):
    def __init__(self, items: list[int]) -> None:
        self._items = list(items)

    def __getitem__(self, index: int | slice) -> NoReturn:
        raise AssertionError("__getitem__ must not be called by rendering")

    def __len__(self) -> int:
        raise AssertionError("__len__ must not be called by rendering")


class TestSequenceImplementationRendersThroughItsFieldNotItsProtocol:
    def test_a_sequence_wrapping_a_private_list_renders_as_an_object_whose_field_is_the_list(
        self, renderer: ValueRenderer
    ) -> None:
        seq = WrappedSequence([1, 2, 3])

        rendered = renderer.render(seq)

        assert rendered == "WrappedSequence(_items=[1, 2, 3])"


# --------------------------------------------------------------------------- #
# 6. An undeclared iterable renders as type name + size, never its elements,  #
#    and its __iter__ is never called. PENDING (no such fast path exists yet #
#    -- today it falls through to ordinary field introspection instead).      #
# --------------------------------------------------------------------------- #
class UndeclaredIterable:
    def __init__(self, items: list[int]) -> None:
        self._items = list(items)
        self.iter_calls = 0

    def __iter__(self) -> Iterator[int]:
        self.iter_calls += 1
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


class TestUndeclaredIterableRendersAsTypeAndSize:
    def test_type_name_and_size_render_with_no_elements_and_iter_never_called(
        self, renderer: ValueRenderer
    ) -> None:
        # Observed RED today: rendering.py has no "is this an undeclared user iterable" fast
        # path at all -- it falls straight through to ordinary field introspection, which shows
        # `UndeclaredIterable(_items=[1, 2, 3], iter_calls=0)` rather than a type+size summary.
        # `__iter__` is already never called (introspection reads `vars()`, not the protocol), so
        # only the output-shape assertion below is what fails.
        iterable = UndeclaredIterable([1, 2, 3])

        rendered = renderer.render(iterable)

        assert iterable.iter_calls == 0
        assert rendered == "UndeclaredIterable (size 3)"


# --------------------------------------------------------------------------- #
# 7. The __narrative_elements__ hook: a test-scope-only stub today (no        #
#    production support), so every behaviour below is PENDING.                #
# --------------------------------------------------------------------------- #
class BoxWithElementsHook:
    """Test-scope stub: `__narrative_elements__` is not read by rendering.py today."""

    def __init__(self, items: list[int]) -> None:
        self._items = list(items)

    def __narrative_elements__(self) -> list[int]:
        return list(self._items)


class BoxWithRaisingElementsHook:
    def __init__(self) -> None:
        self.label = "box"

    def __narrative_elements__(self) -> list[int]:
        raise ValueError("boom")


class _ElementsHookDependency:
    def compute(self) -> int:
        return 55


class BoxWithProxiedElementsHook:
    def __init__(self, dep: _ElementsHookDependency) -> None:
        self.dep = dep

    def __narrative_elements__(self) -> list[int]:
        return [self.dep.compute()]


class _ElementsHookHolderService:
    def receive(self, box: BoxWithProxiedElementsHook) -> None:
        return None


class TestNarrativeElementsHook:
    def test_a_type_declaring_narrative_elements_is_enumerated_by_the_hook_not_its_fields(
        self, renderer: ValueRenderer
    ) -> None:
        # Observed RED today: no code reads `__narrative_elements__` -- the box renders via
        # ordinary field introspection ("BoxWithElementsHook(_items=[10, 20, 30])"), never
        # through the hook.
        box = BoxWithElementsHook([10, 20, 30])

        rendered = renderer.render(box)

        assert "10" in rendered
        assert "20" in rendered
        assert "30" in rendered
        assert "_items" not in rendered

    def test_the_hooks_elements_are_capped_at_the_collection_limit(
        self, renderer: ValueRenderer
    ) -> None:
        # Observed RED today: same absence of hook support -- field introspection shows every
        # element inside `_items` unconditionally (no cap applies to a list-typed field's own
        # contents beyond the collection's own 5-item cap, which is coincidentally also 5, but via
        # the wrong mechanism and with `_items` in the text) rather than a 5-of-7 hook-capped view.
        box = BoxWithElementsHook([100, 101, 102, 103, 104, 105, 106])

        rendered = renderer.render(box)

        assert "100" in rendered
        assert "104" in rendered
        assert "105" not in rendered
        assert "106" not in rendered
        assert "7" in rendered  # the "N total" marker
        assert "_items" not in rendered

    def test_a_hook_calling_a_traced_proxied_method_emits_no_span_and_still_enumerates(
        self,
    ) -> None:
        # Observed RED today: the hook is never invoked, so the proxied dependency's computed
        # value ("55") never appears anywhere -- the box instead renders its raw `dep` field,
        # which recurses into the proxy's own internals ("_nt_target" shows up in the text).
        # The "no span" half already holds today, but only because the hook (and therefore the
        # traced call inside it) never runs at all -- not because of any guard.
        ctx = ContextVarNarrativeContext()
        dep = trace_object(_ElementsHookDependency(), ctx)
        svc = trace_object(_ElementsHookHolderService(), ctx)

        svc.receive(BoxWithProxiedElementsHook(dep))

        roots = ctx.capture_trace().roots
        assert roots[0].children == []  # no phantom span for dep.compute()
        rendered = roots[0].signature.parameters[0].rendered_value
        assert "55" in rendered
        assert "_nt_target" not in rendered

    def test_a_raising_hook_renders_the_typed_error_marker_not_the_objects_fields(
        self, renderer: ValueRenderer
    ) -> None:
        # Observed RED today: the hook is never invoked, so it never raises -- the box renders
        # its real `label` field instead of the "<error: ValueError>" marker every other hook
        # failure in this renderer degrades to (see `_error_marker`).
        box = BoxWithRaisingElementsHook()

        rendered = renderer.render(box)

        assert rendered == "<error: ValueError>"
        assert "label" not in rendered


# --------------------------------------------------------------------------- #
# 8. The narration template resolver invokes a property with a side effect.   #
#    PENDING (`_PropertyPlaceholder.resolve`, `template.py:120-123` -- the    #
#    C-class, unguarded site the scan's test-then-fix order ranks first).     #
# --------------------------------------------------------------------------- #
class OrderWithSideEffectingTotal:
    def __init__(self, base: int) -> None:
        self._base = base
        self.total_reads = 0

    @property
    def total(self) -> int:
        self.total_reads += 1
        return self._base * 2


class TestNarrationTemplatePropertySideEffect:
    def test_resolving_a_property_placeholder_never_invokes_it_and_reads_from_dict_instead(
        self,
    ) -> None:
        # Observed RED today: `_PropertyPlaceholder.resolve` (and `redacted_paths._resolve_segment`
        # it calls first to decide redaction) both do `getattr(obj, "total")`, which invokes the
        # property -- `total_reads` ends up >= 1, and the placeholder resolves to the computed
        # "42" rather than staying an unresolved literal (there is no `total` key in `__dict__`
        # for a state-only read to find).
        order = OrderWithSideEffectingTotal(21)

        result = resolve("total: {order.total}", {"order": order})

        assert order.total_reads == 0
        assert result == "total: {order.total}"


# --------------------------------------------------------------------------- #
# 9. A composite's __repr__/__eq__/__hash__/__lt__ are never invoked by       #
#    rendering (LIVE today -- distinct from the existing __str__-never-       #
#    trusted tests in test_rendering.py's TestNativeStringificationNever      #
#    TrustedForComposites, which this file does not duplicate).               #
# --------------------------------------------------------------------------- #
class SpyComposite:
    def __init__(self, label: str) -> None:
        self.label = label
        self.repr_calls = 0
        self.eq_calls = 0
        self.hash_calls = 0
        self.lt_calls = 0

    def __repr__(self) -> str:
        self.repr_calls += 1
        return f"SpyComposite({self.label!r})"

    def __eq__(self, other: object) -> bool:
        self.eq_calls += 1
        return isinstance(other, SpyComposite) and self.label == other.label

    def __hash__(self) -> int:
        self.hash_calls += 1
        return hash(self.label)

    def __lt__(self, other: object) -> bool:
        self.lt_calls += 1
        return isinstance(other, SpyComposite) and self.label < other.label


class TestCompositeDundersNeverInvokedByRendering:
    def test_repr_is_never_invoked(self, renderer: ValueRenderer) -> None:
        spy = SpyComposite("a")

        renderer.render(spy)

        assert spy.repr_calls == 0

    def test_eq_is_never_invoked_via_dict_membership(self, renderer: ValueRenderer) -> None:
        spy = SpyComposite("a")
        holder = {spy: "value"}
        spy.eq_calls = 0  # reset: constructing the dict above may itself have probed equality

        renderer.render(holder)

        assert spy.eq_calls == 0

    def test_hash_is_never_invoked_via_dict_membership(self, renderer: ValueRenderer) -> None:
        spy = SpyComposite("a")
        holder = {spy: "value"}
        spy.hash_calls = 0  # reset: constructing the dict above already hashed the key once

        renderer.render(holder)

        assert spy.hash_calls == 0

    def test_lt_is_never_invoked_via_sorting(self, renderer: ValueRenderer) -> None:
        a, b = SpyComposite("a"), SpyComposite("b")

        renderer.render([a, b])

        assert a.lt_calls == 0
        assert b.lt_calls == 0


# --------------------------------------------------------------------------- #
# 10. A value carrying no state REFLECTION can read is not thereby a          #
#     stateless leaf: only a platform-defined type's own string conversion is #
#     trusted, every other fieldless value renders as its type name.          #
# --------------------------------------------------------------------------- #
class CStructCredentials(ctypes.Structure):
    """A value whose fields live in C-level descriptors, invisible to `vars()`/`__slots__`:
    scoring it "no instance fields" and trusting its own text hands every field it prints
    straight to the trace, past the deny-list."""

    _fields_ = (("label", ctypes.c_char_p), ("secret", ctypes.c_char_p))

    def __repr__(self) -> str:
        return f"CStructCredentials(label={self.label.decode()}, secret={self.secret.decode()})"


_SIDE_TABLE: dict[int, str] = {}


class SideTableHolder:
    """The same shape without C: state kept outside the instance entirely, in a table keyed by
    identity, so reflection finds nothing while the type's own text prints everything. The call
    counter is a CLASS attribute, never an instance one: an instance field would destroy the very
    fieldlessness this fixture exists to hold."""

    __slots__ = ()

    repr_calls = 0

    def __init__(self, secret: str) -> None:
        _SIDE_TABLE[id(self)] = secret

    def __repr__(self) -> str:
        type(self).repr_calls += 1
        return f"SideTableHolder(secret={_SIDE_TABLE[id(self)]})"


class TestFieldlessValueIsNeverDescribedByItsOwnText:
    def test_a_c_struct_renders_as_its_type_name_in_both_channels(
        self, renderer: ValueRenderer
    ) -> None:
        value = CStructCredentials(b"prod-db", b"LEAK-TOKEN-cstruct")

        rendered = renderer.render(value)
        structured = renderer.render_structured(value)
        captured, structured_capture, _ = renderer.render_for_capture(value)

        assert rendered == "<CStructCredentials>"
        assert structured == StringVal("<CStructCredentials>")
        assert captured == "<CStructCredentials>"
        assert structured_capture == StringVal("<CStructCredentials>")

    def test_a_side_table_holder_renders_as_its_type_name_and_its_repr_never_runs(
        self, renderer: ValueRenderer
    ) -> None:
        value = SideTableHolder("LEAK-TOKEN-side-table")
        SideTableHolder.repr_calls = 0

        rendered = renderer.render(value)
        structured = renderer.render_structured(value)

        assert rendered == "<SideTableHolder>"
        assert structured == StringVal("<SideTableHolder>")
        assert SideTableHolder.repr_calls == 0

    def test_a_fieldless_value_nested_in_a_field_renders_as_its_type_name(
        self, renderer: ValueRenderer
    ) -> None:
        @dataclasses.dataclass
        class Envelope:
            payload: object

        rendered = renderer.render(Envelope(CStructCredentials(b"prod-db", b"LEAK-TOKEN-nested")))

        assert rendered == "Envelope(payload=<CStructCredentials>)"

    def test_a_platform_leaf_still_renders_through_its_own_string_conversion(
        self, renderer: ValueRenderer
    ) -> None:
        # The other half of the rule: trust is granted by ORIGIN, so the standard library's own
        # value types keep their text -- a fieldless-value guard that swallowed those would be a
        # regression in every trace, not a fix.
        assert renderer.render(uuid.UUID(int=7)) == "00000000-0000-0000-0000-000000000007"
        assert renderer.render(decimal.Decimal("1.50")) == "1.50"
        assert renderer.render(pathlib.PurePosixPath("/srv/data")) == "/srv/data"
        assert renderer.render(datetime.date(2024, 1, 31)) == "2024-01-31"
        assert renderer.render(range(3)) == "range(0, 3)"
