# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Eager object-to-string renderer used at capture time.

``ValueRenderer``. Produces stable textual snapshots (``render``) so later renderers
and exporters never inspect live objects, plus a type-preserving companion (``render_structured``
→ :class:`RenderedValue`) for typed OTel export.

Handled: truncation, collections, dicts, dataclass/attrs/plain-object/``NamedTuple`` introspection
with redact-by-default field-name hiding, ``concurrent.futures`` / ``asyncio`` future state
markers, awaitable ``<pending>``, cycle markers, depth limiting, and the ``@narrative_summary``
method hook. Every string leaf is control-sanitised.

**Native stringification is never trusted for a composite** (family-wide fix, 2026-09-11): a
plain object exposing instance state (``__dict__`` or ``__slots__``) is introspected field-by-field
regardless of a custom ``__str__``/``__repr__`` override. Before this fix, the shape decision asked
only "does this type override ``__str__``", so a hand-written ``__str__`` that interpolated a
sensitive field (or a nested object's own hostile ``__str__``) ran completely unmediated -- past
redact-by-name, the deny-list, depth caps, everything. Dict KEYS are
rendered through this same pipeline (redaction-by-name and introspection both apply to a key, not
just its value), rather than a bare ``str(key)`` that bypassed every guard unconditionally. When a
``@narrative_summary`` method, a custom ``__str__``, or an object's own field getter raises, that
one part renders ``<error: <TypeName>>`` -- the exception's own type name, never ``str(exc)``
(a message can carry the very value that failed to render).

**Platform-defined types are trusted for native stringification even though they carry state**:
the "never trust a composite's own stringification" rule above is correct for application types
but too broad for the standard library's own value types -- ``pathlib.Path``, ``datetime``,
``decimal.Decimal``, ``uuid.UUID``, ``fractions.Fraction`` and ``ipaddress.*`` all carry instance
state (populated ``__slots__``) and were walked field-by-field into unreadable or inaccessible
output. ``_is_platform_type`` decides by ORIGIN, never by name: a type whose ``__module__`` names
a top-level standard-library package (``sys.stdlib_module_names``), or whose C implementation is
not a heap type at all (a genuine interpreter built-in), is trusted; a user subclass of a platform
type is not, because a subclass's own ``__module__`` is wherever *it* was defined, never inherited
from its base. A user class that merely shares a platform type's name is not trusted either -- the
identity test never looks at the name. Same reasoning as Java's ``PLATFORM_DEFINED`` (keyed on
defining class loader) and .NET's (keyed on defining assembly); the trusted text is still
scanned, escaped and capped, and still redacted by field NAME first -- a field or parameter named
``token`` typed ``pathlib.Path`` still renders ``[REDACTED]``.

**Platform origin is the ONLY thing that earns a value its own string conversion** -- never "this
value has no field I can see". Carrying no readable instance state used to be read as "a stateless
leaf", the one shape whose own ``str()`` rendering may call, and that inference is false: a
``ctypes.Structure`` subclass holds its fields in C-level descriptors, an extension type holds
them in a C struct, an ordinary class can hold them in a module-level table keyed by identity or
in a closure -- ``vars()`` is empty for all three while their own ``__repr__`` prints every field
they hold, straight past redaction into the trace. Emptiness is therefore not evidence of nothing
to hide; it is most often evidence of state this renderer cannot reach. Such a value renders as
its type name alone (``<TypeName>``): visible as a value, bounded, unread. See :func:`_shape_of`,
the single decision both channels share.

Depth limiting (a security fuzz suite finding): an identity-based cycle guard answers "have I been
here before", never "how deep am I" -- a linear chain of distinct objects never repeats an
identity, so the guard alone let a 10,000-node chain recurse Python's interpreter past its stack
limit, escaping as an uncaught ``RecursionError``. ``MAX_DEPTH`` (32) is the fourth cap beside the
200-character string limit, the 5-element collection limit and the 5-field object limit; a value
beyond it renders as ``<max-depth>`` -- unreached, so a redacted component past the cap is never
printed, not even partially.

``NamedTuple`` is introspected by field name rather than rendered as an anonymous positional
collection (the template-resolution family, Java's wrapper-``toString()`` bug class applied to a
Python-only shape): being a ``tuple`` subclass, it would otherwise reach ``_render_collection``
first and print every field's raw value with no redaction check at all, since a collection
element carries no name to redact by.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import dataclasses
import inspect
import sys
from collections.abc import Callable, Collection, Iterable, Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any, ClassVar, cast

from narrativetrace.escape import control_sanitize
from narrativetrace.markers import is_field_not_traced
from narrativetrace.redaction import REDACTED_MARKER, RedactionPolicy
from narrativetrace.values import (
    BoolVal,
    FloatVal,
    IntVal,
    ListVal,
    NullVal,
    ObjectVal,
    RenderedValue,
    StringVal,
)

_DEFAULT_MAX_STRING_LENGTH = 200
_DEFAULT_MAX_COLLECTION_ITEMS = 5
_DEFAULT_MAX_OBJECT_FIELDS = 5

_NARRATIVE_SUMMARY_ATTR = "__nt_narrative_summary__"

_ELEMENTS_HOOK = "__narrative_elements__"
"""The third sanctioned rendering hook (the rendering rule: rendering reads state, never runs
behaviour), alongside ``@narrative_summary`` and a platform value's own ``__str__``: a type
declaring this dunder method is trusted to enumerate its own elements -- the one case this
renderer runs a type's own iteration, because the author declared it pure. Checked ahead of the
platform-origin collection/map dispatch in :meth:`ValueRenderer._render_if_enumerable`, guarded by
the same cycle detection, capped by the same :attr:`ValueRenderer.max_collection_items`, and
totality-guarded like every other element walk -- a throwing hook degrades to the typed
``<error: TypeName>`` marker, never the object's own fields."""

_COLLECTION_TYPES = (list, tuple, set, frozenset)

STATE_MISSING = object()
"""Sentinel returned by :func:`read_backing_field` when a name names no readable state -- a
genuinely computed ``@property``, a missing member, or a zero-arg method with nothing stored
under that name. Public: :mod:`narrativetrace.template` and :mod:`narrativetrace.redacted_paths`
both need to tell "no state to read" apart from a real, stored ``None``."""

_TOO_DEEP = "<max-depth>"
_TOO_MANY = "<max-nodes>"
"""Rendered in place of a value once one walk has rendered :data:`_MAX_NODES` values (B-185)."""

_MAX_NODES = 1024
"""How many values one walk renders, at most. On the scale of the per-level caps: a full five-wide
tree four levels deep is 781 values, already more than a reader scans in one parameter; 1024 is the
next round number above it. Scalars count too, and the count comes before the scalar split, so the
flat and structured paths -- which classify a few leaves differently -- keep identical budgets."""

_REPEAT_MIN_NODES = 8
"""The smallest completed rendering, in values, that a later reference to the same instance points
back to (``<repeat: TypeName>``) instead of repeating. A smaller one is as cheap to repeat as to
point at, and reads better repeated."""

_TRUSTED_NUMERIC_TYPES = (int, float)

_HEAP_TYPE_FLAG = 1 << 9
"""``Py_TPFLAGS_HEAPTYPE``: set on every ordinary Python class, clear only on a type allocated
statically inside the interpreter (``int``, ``str``, ``datetime.datetime``, ...). A stable CPython
ABI flag, not a private implementation detail."""

_RENDERING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "narrativetrace_rendering", default=False
)
"""Marks that a :class:`ValueRenderer` public entry point is executing right now, on the current
thread or asyncio task (cross-port finding, Java's ``RenderingGuard``).

Java's bug: reflectively invoking a *woven* record accessor during parameter/return capture ran
that accessor's own instrumented bytecode, opening a span for a call the application never made.
Python has no bytecode weaving -- tracing here is entirely :func:`~narrativetrace.trace_object
.trace_object`'s proxy -- but the same shape of hazard reaches it differently: a value being
rendered exposes a hook that runs arbitrary application code (the ``@narrative_summary`` method,
or -- for a value whose ORIGIN earns it its own text, since neither a composite's nor a fieldless
value's ``__str__``/``__repr__`` is trusted, see the module docstring -- that own ``__str__``,
which an enum member or a platform subclass can still override), and that hook calls a method on
an object held as a field or closure that is itself wrapped by ``trace_object``. Calling that
wrapped method through ``_TracedProxy.__getattr__`` genuinely dispatches into the proxy's call
wrapper, opening and closing a real span for it -- attributed as a root when rendering runs during
parameter capture (before ``enter_method``), or nested under the very call being rendered when it
runs on the return value (rendered while that call's own span is still the active-stack top, before
``exit_method_with_return`` pops it).

Checked by :func:`~narrativetrace.trace_object.trace_object`'s call wrapper (:func:`is_rendering`)
right alongside ``context.is_active()`` -- the same fast-path shape, one more condition -- so a
call made *by* rendering delegates raw instead of opening a span. Genuine calls the traced method's
own BODY makes are unaffected: the flag is only ever set for the duration of a
:class:`ValueRenderer` entry point, never for the traced call itself.

A :class:`contextvars.ContextVar`, not a plain module global or a bare ``threading.local``: a
fresh thread gets its own copy for free (Python threads do not share a ``Context`` by default),
and an asyncio task gets an isolated copy of whatever was set at the moment it was created --
never a mutation a concurrently scheduled sibling task makes afterwards. It nests (B-186, Java's
depth counter): the narrative-summary hook is a sanctioned door into user code, and what it reaches
may render a value of its own -- another :class:`ValueRenderer`, a ``{obj.prop}`` template -- each
running its own :func:`rendering_scope` pair inside the outer one. :func:`rendering_scope` resets by
token, so an inner exit restores exactly what the inner entry found and the guard stays up for the
rest of the outer walk; only the outermost exit clears it. The variable is a plain ``bool`` because
the token carries the nesting, not a stored count.
"""


def is_rendering() -> bool:
    """Whether the calling thread/task is currently inside a :class:`ValueRenderer` entry point.

    Read by :func:`~narrativetrace.trace_object.trace_object`'s call wrapper before dispatching a
    traced call -- a plain, non-throwing, non-blocking read, same contract as
    ``context.is_active()`` beside which it is checked.
    """
    return _RENDERING.get()


@contextmanager
def rendering_scope() -> Iterator[None]:
    """Marks the calling thread/task as rendering for the duration of the ``with`` block.

    Wraps every :class:`ValueRenderer` PUBLIC entry point (:meth:`ValueRenderer.render`,
    :meth:`ValueRenderer.render_structured`, :meth:`ValueRenderer.render_for_capture`) -- never
    the internal ``_render*`` recursion, which would just re-enter this scope pointlessly on every
    nested value -- plus :mod:`narrativetrace.template`'s own reflective backing-field read for a
    ``{obj.prop}`` placeholder, a second, cross-module caller with the identical hazard (a hook it
    might still fall back to could call a traced object). Public, not module-private, for exactly
    that second caller. Token-based reset (rather than blindly setting ``False``) so the one
    legitimate nesting case -- ``render_for_capture`` calling ``render``/``render_structured`` --
    restores the outer call's own state exactly, not a hardcoded default.
    """
    token = _RENDERING.set(True)
    try:
        yield
    finally:
        _RENDERING.reset(token)


class _RenderWalk:
    """One render call's recursion state: identity ancestry, remaining depth budget, the total
    node budget, the memo of completed renderings and the summary hook's answers.

    ``RenderWalk``. The ancestry answers "have I been here before" (cycles), the depth "how deep
    am I" (stack safety), the budget and the memo "how much have I rendered" (B-185: the cycle
    guard drops an ancestor on the way out so a shared object may render twice, and when the
    sharing repeats down a graph every rung doubles the walk). All unwind or advance in the same
    funnel, so one object owns them rather than threading parameters through every recursive
    method. Values the memo and the summary cache remember are held by reference, so an identity
    can never be reused by a temporary the walk has already let go of.
    """

    __slots__ = ("_ancestors", "_depth", "_nodes", "_repeats", "_summaries")

    def __init__(self) -> None:
        self._ancestors: set[int] = set()
        self._depth = 0
        self._nodes = 0
        self._repeats: dict[int, object] = {}
        self._summaries: dict[int, tuple[object, str]] = {}

    def next_path(self) -> _RenderWalk:
        """A fresh walk for the second render path of the same capture: nothing of this walk's
        path, memo or budget, only the summary hook's answers."""
        walk = _RenderWalk()
        walk._summaries = self._summaries
        return walk

    def seen(self, value: object) -> bool:
        """Whether ``value`` is already an ancestor on the current path (a cycle)."""
        return id(value) in self._ancestors

    def enter(self, value: object) -> None:
        """Marks ``value`` as an ancestor of whatever is rendered next."""
        self._ancestors.add(id(value))

    def exit(self, value: object) -> None:
        """Un-marks ``value`` once its subtree has finished rendering."""
        self._ancestors.discard(id(value))

    def is_repeat(self, value: object) -> bool:
        """Whether ``value`` already rendered in full earlier in this walk."""
        return id(value) in self._repeats

    def rendered(self, value: object, nodes_before: int) -> None:
        """Remembers that ``value`` rendered to completion, when that rendering was large enough
        to be worth pointing back to. The root is never remembered: it cannot be reached again
        except as a cycle, which the ancestor half already answers."""
        if self._depth == 0 or self._nodes - nodes_before + 1 < _REPEAT_MIN_NODES:
            return
        self._repeats.setdefault(id(value), value)

    def count(self) -> bool:
        """Counts one more rendered value against :data:`_MAX_NODES`; ``False`` means the caller
        renders the node-budget marker instead of the value."""
        if self._nodes >= _MAX_NODES:
            return False
        self._nodes += 1
        return True

    def nodes(self) -> int:
        """How many values this walk has counted so far."""
        return self._nodes

    def cached_summary(self, value: object) -> str | None:
        """The summary hook's answer for ``value`` earlier in this capture, or ``None``."""
        entry = self._summaries.get(id(value))
        return None if entry is None else entry[1]

    def cache_summary(self, value: object, text: str) -> None:
        """Records the summary hook's answer for ``value``, for the rest of this capture."""
        self._summaries[id(value)] = (value, text)

    def descend(self) -> bool:
        """Claims one level of depth budget; ``False`` once :data:`ValueRenderer.MAX_DEPTH` is
        spent, so the caller renders the ``<max-depth>`` marker instead of recursing further."""
        if self._depth >= ValueRenderer.MAX_DEPTH:
            return False
        self._depth += 1
        return True

    def ascend(self) -> None:
        """Returns one level of depth budget on the way back up the call stack."""
        self._depth -= 1


def _repeat_marker(value: object) -> str:
    """``<repeat: TypeName>``: the same instance, shown above -- deterministic, so goldens hold."""
    return f"<repeat: {type(value).__name__}>"


class ValueRenderer:
    """Renders live values to flat strings and structured :class:`RenderedValue`s."""

    MAX_DEPTH: ClassVar[int] = 32
    """Recursion cap for nested containers/objects (a security fuzz suite finding)."""

    def __init__(
        self,
        max_string_length: int = _DEFAULT_MAX_STRING_LENGTH,
        max_collection_items: int = _DEFAULT_MAX_COLLECTION_ITEMS,
        max_object_fields: int = _DEFAULT_MAX_OBJECT_FIELDS,
        redaction_policy: RedactionPolicy | None = None,
    ) -> None:
        self.max_string_length = max_string_length
        self.max_collection_items = max_collection_items
        self.max_object_fields = max_object_fields
        self.redaction_policy = (
            redaction_policy if redaction_policy is not None else RedactionPolicy.DEFAULT
        )

    # ------------------------------------------------------------------ #
    # Flat rendering                                                      #
    # ------------------------------------------------------------------ #
    def render(self, value: object) -> str:
        """Renders ``value`` to a stable, bounded, control-sanitised string."""
        with rendering_scope():
            try:
                return self._render(value, _RenderWalk())
            except Exception:  # the renderer is total: nothing a value does may escape capture
                return f"<{type(value).__name__}>"

    def _render(self, value: object, walk: _RenderWalk) -> str:
        # Counted before the scalar split: the two paths classify a few leaves differently, and
        # counting every value rendered keeps their budgets, and so their back-references, equal.
        if not walk.count():
            return _TOO_MANY
        scalar = self._render_scalar(value)
        return scalar if scalar is not None else self._render_guarded(value, walk)

    def _render_scalar(self, value: object) -> str | None:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, str):
            return self._render_string(value)
        if isinstance(value, (int, float)):
            scalar = self._render_number(value)
            if scalar is not None:
                return scalar
        if isinstance(value, Enum):
            return self._render_with_str(value)  # no trusted built-in Enum: __str__ is overridable
        return None

    def _render_guarded(self, value: object, walk: _RenderWalk) -> str:
        """The back-reference, one level deeper, or the depth marker. Only a rendering that
        completed is remembered: one that raised is not, and one refused by the depth cap never
        began, so a later, shallower reference to the same instance renders it in full."""
        if walk.is_repeat(value):
            return _repeat_marker(value)
        if not walk.descend():
            return _TOO_DEEP
        nodes_before = walk.nodes()
        try:
            rendered = self._render_complex(value, walk)
        finally:
            walk.ascend()
        walk.rendered(value, nodes_before)
        return rendered

    def _render_structured_string(self, value: str) -> RenderedValue:
        if self.redaction_policy.should_redact_value(value):
            return StringVal(REDACTED_MARKER)
        return StringVal(value)

    def _render_structured_int(self, value: int) -> RenderedValue | None:
        # Extending int says nothing about what a value holds: only the exact platform type is a
        # scalar here. Returning None (not IntVal/StringVal) is "not a scalar", the same "not
        # mine" idiom every other fast path in this class uses to hand off to the walk below.
        return IntVal(value) if _is_trusted_numeric(value) else None

    def _render_structured_float(self, value: float) -> RenderedValue | None:
        return FloatVal(value) if _is_trusted_numeric(value) else None

    def _render_number(self, value: int | float) -> str | None:
        """``value``'s own text, or ``None`` when ``value`` is not the exact platform type.

        Extending ``int``/``float`` says nothing about what a value holds: a subclass is an
        ordinary composite with a numeric base, free to carry a deny-listed field and print it
        from a ``__str__`` its author wrote long before anyone traced the class. A fast path that
        read that text unconditionally had only the redaction-by-shape scan and the length cap in
        front of it -- no field name for the deny-list to match, no ``@not_traced`` to honor, none
        of the caps a walked composite obeys. So only the platform's own leaf types are read here;
        ``None`` hands every other case to :meth:`_render_complex`, where a composite belongs, on
        both this channel and the structured one alike (see :func:`_shape_of`).
        """
        return str(value) if _is_trusted_numeric(value) else None

    def _render_string(self, value: str) -> str:
        if self.redaction_policy.should_redact_value(value):
            return REDACTED_MARKER
        return self._render_string_body(value)

    def _render_string_body(self, value: str) -> str:
        """The quoted, sanitised, length-capped rendering of a string already known not to be
        value-shape redacted -- shared by :meth:`_render_string` and :meth:`render_for_capture`,
        so a string's shape is checked once per call site rather than re-derived."""
        safe = control_sanitize(value)
        if len(safe) > self.max_string_length:
            return f'"{safe[: self.max_string_length]}…"'
        return f'"{safe}"'

    def render_narration_text(self, text: str) -> str:
        """Renders text substituted into a narration: exactly what a captured string gets —
        value-shape redaction, control sanitising, the string cap — minus the quotation marks a
        narration must not carry (2026-09-04, family security fix: template substitution used to
        print text via its own ``str()``, so a JWT rendered ``[REDACTED]`` as an argument and in
        full through ``@narrated("issued {token}")``)."""
        if self.redaction_policy.should_redact_value(text):
            return REDACTED_MARKER
        safe = control_sanitize(text)
        if len(safe) > self.max_string_length:
            return f"{safe[: self.max_string_length]}…"
        return safe

    def _render_complex(self, value: object, walk: _RenderWalk) -> str:
        if self._is_future(value):
            return self._render_future(value, walk)
        if inspect.isawaitable(value):
            return "<pending>"
        enumerated = self._render_if_enumerable(value, walk)
        if enumerated is not None:
            return enumerated
        summary = self._render_summary(value, walk)
        if summary is not None:
            return summary
        shape = _shape_of(value)
        if shape is _Shape.FIELDS:
            return self._render_introspected(value, walk)
        if shape is _Shape.OWN_STRING:
            return self._render_with_str(value)
        return _opaque_marker(value)

    def _render_if_enumerable(self, value: object, walk: _RenderWalk) -> str | None:
        """Collections, maps and bare iterables, dispatched by ORIGIN rather than bare
        ``isinstance`` alone (the rendering rule: rendering reads state, never runs behaviour): an
        exact platform collection/map enumerates through its own state, unchanged; a user SUBCLASS
        of a concrete platform collection (``list``, ``dict``) enumerates through that ancestor's
        own state read (``list.__iter__``/``dict.items``, unbound on the base type, bypassing the
        subclass's override) rather than the subclass's own, possibly hostile, override; a
        hand-rolled ``Collection`` (no platform ancestor -- ``isinstance(value, Collection)`` true
        through the type's own ``__len__``/``__iter__``/``__contains__``, e.g. a
        ``collections.abc.Sequence`` implementation) is not enumerated here at all, so the caller
        falls through to plain object introspection of its own fields, never a call that could be
        overridden; a bare ``Iterable`` that is not a full ``Collection`` (missing
        ``__contains__``, so nothing here implies it is safe to walk) renders a bounded type+size
        marker, never touching its iterator.

        Returns ``None`` when the caller should fall through to the summary/introspection path.
        """
        origin = _enumeration_of(value)
        if origin is _Enumeration.DECLARED:
            return self._render_elements_hook(value, walk)
        if origin is _Enumeration.COLLECTION:
            return self._render_collection(value, walk)
        if origin is _Enumeration.MAP:
            return self._render_map(cast("dict[Any, Any]", value), walk)
        if origin is _Enumeration.BARE_ITERABLE:
            return _bare_iterable_marker(value)
        return None

    def _render_elements_hook(self, value: object, walk: _RenderWalk) -> str:
        if walk.seen(value):
            return _identity_marker(value)
        walk.enter(value)
        try:
            return self._render_elements_hook_body(value, walk)
        finally:
            walk.exit(value)

    def _render_elements_hook_body(self, value: object, walk: _RenderWalk) -> str:
        try:
            items = list(getattr(value, _ELEMENTS_HOOK)())
        except Exception as exc:  # a rogue hook must not break capture
            return _error_marker(exc)
        return self._render_capped_items(items, walk)

    def _render_collection(self, value: Any, walk: _RenderWalk) -> str:
        if walk.seen(value):
            return _identity_marker(value)
        walk.enter(value)
        try:
            return self._render_collection_body(value, walk)
        finally:
            walk.exit(value)

    def _render_collection_body(self, value: Any, walk: _RenderWalk) -> str:
        try:
            items = _collection_elements(value)
        except Exception:  # a rogue iterator must not break capture
            return f"<{type(value).__name__}>"
        return self._render_capped_items(items, walk)

    def _render_capped_items(self, items: list[object], walk: _RenderWalk) -> str:
        shown = ", ".join(
            self._render_element(item, walk) for item in items[: self.max_collection_items]
        )
        if len(items) > self.max_collection_items:
            return f"[{shown}, … ({len(items)} total)]"
        return f"[{shown}]"

    def _render_element(self, item: object, walk: _RenderWalk) -> str:
        try:
            return self._render(item, walk)
        except Exception:  # one bad element must not poison its siblings
            return f"<{type(item).__name__}>"

    def _render_map(self, value: dict[Any, Any], walk: _RenderWalk) -> str:
        if walk.seen(value):
            return _identity_marker(value)
        walk.enter(value)
        try:
            return self._render_map_body(value, walk)
        finally:
            walk.exit(value)

    def _render_map_body(self, value: dict[Any, Any], walk: _RenderWalk) -> str:
        try:
            items = _map_items(value)
        except Exception:  # a rogue Mapping must not break capture
            return f"<{type(value).__name__}>"
        entries = [
            self._render_map_entry(key, item, walk)
            for key, item in items[: self.max_collection_items]
        ]
        joined = ", ".join(entries)
        if len(items) > self.max_collection_items:
            return f"{{{joined}, …}}"
        return f"{{{joined}}}"

    def _render_map_entry(self, key: object, item: object, walk: _RenderWalk) -> str:
        rendered_key = self._render_map_key(key, walk)
        rendered = (
            REDACTED_MARKER
            if self.redaction_policy.should_redact(rendered_key)
            else self._render_element(item, walk)
        )
        return f"{rendered_key}={rendered}"

    def _render_map_key(self, key: object, walk: _RenderWalk) -> str:
        """Renders a dict KEY through the same pipeline as a value -- introspection and
        redaction-by-name both apply to a key, not just a bare, unmediated ``str(key)`` (a
        family-wide fix, 2026-09-11: a sensitive object used as a key used to leak
        unconditionally, since a raw ``str()`` never asked the deny-list anything)."""
        try:
            return self._render(key, walk)
        except Exception as exc:  # a rogue key must not break capture
            return _error_marker(exc)

    def _render_introspected(self, value: object, walk: _RenderWalk) -> str:
        if walk.seen(value):
            return _identity_marker(value)
        walk.enter(value)
        try:
            names = _field_names(value)
            limit = min(len(names), self.max_object_fields)
            parts = [self._render_field(value, name, walk) for name in names[:limit]]
            joined = ", ".join(parts)
            suffix = ", …" if len(names) > self.max_object_fields else ""
            return f"{type(value).__name__}({joined}{suffix})"
        finally:
            walk.exit(value)

    def _render_field(self, value: object, name: str, walk: _RenderWalk) -> str:
        annotated = is_field_not_traced(type(value), name)
        if self.redaction_policy.is_redacted(name, annotated=annotated):
            return f"{name}={REDACTED_MARKER}"
        try:
            return f"{name}={self._render(getattr(value, name), walk)}"
        except Exception as exc:  # a rogue getter must not break capture
            return f"{name}={_error_marker(exc)}"

    def _render_with_str(self, value: object) -> str:
        try:
            safe = control_sanitize(str(value))
        except Exception as exc:  # a rogue __str__ may raise anything
            return _error_marker(exc)
        if len(safe) > self.max_string_length:
            return f"{safe[: self.max_string_length]}…"
        return safe

    def _render_future(self, value: object, walk: _RenderWalk) -> str:
        future: Any = value
        try:
            is_done = future.done()
        except Exception:  # a rogue Future must not break capture
            return "<failed>"
        if not is_done:
            return "<pending>"
        try:
            is_cancelled = future.cancelled()
        except Exception:
            return "<failed>"
        if is_cancelled:
            return "<cancelled>"
        try:
            return self._render(future.result(), walk)
        except Exception:  # failed dereference renders a marker
            return "<failed>"

    def _render_summary(self, value: object, walk: _RenderWalk) -> str | None:
        """The ``@narrative_summary`` hook's text, run at most once per instance per capture: the
        walk caches the answer, failure marker included, and :meth:`render_for_capture` hands the
        cache from the flat walk to the structured one, so a hook with a side effect is not
        repeated by tracing."""
        method = _find_summary_method(type(value))
        if method is None:
            return None
        cached = walk.cached_summary(value)
        if cached is not None:
            return cached
        try:
            text = str(method(value))
        except Exception as exc:  # a broken summary is an error, not a silent fallback
            text = _error_marker(exc)
        walk.cache_summary(value, text)
        return text

    # ------------------------------------------------------------------ #
    # Structured rendering                                                #
    # ------------------------------------------------------------------ #
    def render_structured(self, value: object) -> RenderedValue:
        """Renders ``value`` preserving its Python type as a :class:`RenderedValue`."""
        with rendering_scope():
            try:
                return self._render_structured(value, _RenderWalk())
            except Exception:  # the renderer is total: nothing a value does may escape capture
                return StringVal(f"<{type(value).__name__}>")

    # ------------------------------------------------------------------ #
    # Capture-oriented rendering                                          #
    # ------------------------------------------------------------------ #
    def render_for_capture(self, value: object) -> tuple[str, RenderedValue, bool]:
        """Renders ``value`` for a :class:`~narrativetrace.signature.ParameterCapture`, reporting
        alongside the usual text and structured renderings whether value-SHAPE redaction consumed
        the value whole -- the fact :meth:`~narrativetrace.trace_object._build_capture` needs to
        set ``ParameterCapture.redacted`` truthfully for a parameter caught by shape (a JWT, a
        Luhn-valid PAN, a national-id checksum) rather than by name (``trace_object`` already
        short-circuits the name axis before any rendering happens, so it never calls this).

        ``shape_redacted`` is true only when ``value`` is ITSELF a top-level string whose shape
        matched -- the one case where the entire rendered text IS the marker because there was
        nothing else to render. A shape match on a NESTED leaf (a JWT inside a dataclass field, a
        dict value) still masks that leaf in the text below (``_render_string``/
        ``_render_structured_string`` run the identical check for it, unconditionally, same as
        ever) but leaves ``shape_redacted`` here ``False``: the flag is per-PARAMETER, matches are
        per-leaf, and setting it for a partially-redacted object would claim the whole value was
        withheld when only one field was.

        Computed directly at the only place a whole-value shape match can occur -- never by
        comparing the finished text to :data:`REDACTED_MARKER` afterwards, which would misfire on
        an ordinary string whose content happens to equal the marker literally, and would have
        nothing to compare at all for a non-string value. The string case checks the shape once
        here and reuses it for both the text and structured renderings below (rather than letting
        each re-derive it independently, as calling :meth:`render` and :meth:`render_structured`
        separately would); a non-string value has no top-level shape check to share, so it simply
        delegates to both.
        """
        with rendering_scope():
            try:
                if isinstance(value, str):
                    shape_redacted = self.redaction_policy.should_redact_value(value)
                    if shape_redacted:
                        return REDACTED_MARKER, StringVal(REDACTED_MARKER), True
                    return self._render_string_body(value), StringVal(value), False
                walk = _RenderWalk()
                try:
                    flat = self._render(value, walk)
                except Exception:  # each path is total on its own
                    flat = f"<{type(value).__name__}>"
                try:
                    structured = self._render_structured(value, walk.next_path())
                except Exception:
                    structured = StringVal(f"<{type(value).__name__}>")
                return flat, structured, False
            except Exception:  # the renderer is total: nothing a value does may escape capture
                marker = f"<{type(value).__name__}>"
                return marker, StringVal(marker), False

    def _render_structured(self, value: object, walk: _RenderWalk) -> RenderedValue:
        if not walk.count():
            return StringVal(_TOO_MANY)
        scalar = self._render_structured_scalar(value)
        return scalar if scalar is not None else self._render_structured_guarded(value, walk)

    def _render_structured_scalar(self, value: object) -> RenderedValue | None:
        if value is None:
            return NullVal()
        if isinstance(value, bool):
            return BoolVal(value)
        if isinstance(value, str):
            return self._render_structured_string(value)
        if isinstance(value, int):
            structured_int = self._render_structured_int(value)
            if structured_int is not None:
                return structured_int
        if isinstance(value, float):
            structured_float = self._render_structured_float(value)
            if structured_float is not None:
                return structured_float
        if isinstance(value, Enum):
            return StringVal(self._render_with_str(value))
        return None

    def _render_structured_guarded(self, value: object, walk: _RenderWalk) -> RenderedValue:
        """Structured twin of :meth:`_render_guarded`: the same decision in the same order."""
        if walk.is_repeat(value):
            return StringVal(_repeat_marker(value))
        if not walk.descend():
            return StringVal(_TOO_DEEP)
        nodes_before = walk.nodes()
        try:
            rendered = self._render_structured_complex(value, walk)
        finally:
            walk.ascend()
        walk.rendered(value, nodes_before)
        return rendered

    def _render_structured_complex(self, value: object, walk: _RenderWalk) -> RenderedValue:
        if self._is_future(value):
            return self._render_structured_future(value, walk)
        if inspect.isawaitable(value):
            return StringVal("<pending>")
        enumerated = self._render_structured_if_enumerable(value, walk)
        if enumerated is not None:
            return enumerated
        summary = self._render_summary(value, walk)
        if summary is not None:
            return StringVal(summary)
        shape = _shape_of(value)
        if shape is _Shape.FIELDS:
            return self._render_structured_object(value, walk)
        if shape is _Shape.OWN_STRING:
            return StringVal(self._render_with_str(value))
        return StringVal(_opaque_marker(value))

    def _render_structured_if_enumerable(
        self, value: object, walk: _RenderWalk
    ) -> RenderedValue | None:
        """Structured twin of :meth:`_render_if_enumerable`: asks the SAME verdict
        (:func:`_enumeration_of`) and only encodes the answer as a :class:`RenderedValue`."""
        origin = _enumeration_of(value)
        if origin is _Enumeration.DECLARED:
            return self._render_structured_elements_hook(value, walk)
        if origin is _Enumeration.COLLECTION:
            return self._render_structured_collection(value, walk)
        if origin is _Enumeration.MAP:
            return self._render_structured_map(cast("dict[Any, Any]", value), walk)
        if origin is _Enumeration.BARE_ITERABLE:
            return StringVal(_bare_iterable_marker(value))
        return None

    def _render_structured_elements_hook(self, value: object, walk: _RenderWalk) -> RenderedValue:
        if walk.seen(value):
            return StringVal(_identity_marker(value))
        walk.enter(value)
        try:
            try:
                items = list(getattr(value, _ELEMENTS_HOOK)())
            except Exception as exc:  # a rogue hook must not break capture
                return StringVal(_error_marker(exc))
            return self._render_structured_items(items, walk)
        finally:
            walk.exit(value)

    def _render_structured_items(self, items: list[object], walk: _RenderWalk) -> RenderedValue:
        shown = items[: self.max_collection_items]
        return ListVal([self._render_structured_element(item, walk) for item in shown])

    def _render_structured_collection(self, value: Any, walk: _RenderWalk) -> RenderedValue:
        if walk.seen(value):
            return StringVal(_identity_marker(value))
        walk.enter(value)
        try:
            return self._render_structured_collection_body(value, walk)
        finally:
            walk.exit(value)

    def _render_structured_collection_body(self, value: Any, walk: _RenderWalk) -> RenderedValue:
        try:
            items = _collection_elements(value)
        except Exception:  # a rogue iterator must not break capture
            return StringVal(f"<{type(value).__name__}>")
        return self._render_structured_items(items, walk)

    def _render_structured_element(self, item: object, walk: _RenderWalk) -> RenderedValue:
        try:
            return self._render_structured(item, walk)
        except Exception:  # one bad element must not poison its siblings
            return StringVal(f"<{type(item).__name__}>")

    def _render_structured_map(self, value: dict[Any, Any], walk: _RenderWalk) -> RenderedValue:
        if walk.seen(value):
            return StringVal(_identity_marker(value))
        walk.enter(value)
        try:
            return self._render_structured_map_body(value, walk)
        finally:
            walk.exit(value)

    def _render_structured_map_body(
        self, value: dict[Any, Any], walk: _RenderWalk
    ) -> RenderedValue:
        try:
            items = _map_items(value)
        except Exception:  # a rogue Mapping must not break capture
            return StringVal(f"<{type(value).__name__}>")
        fields: dict[str, RenderedValue] = {}
        for key, item in items[: self.max_collection_items]:
            key_name, rendered = self._render_structured_map_entry(key, item, walk)
            fields[key_name] = rendered
        return ObjectVal("Map", fields)

    def _render_structured_map_entry(
        self, key: object, item: object, walk: _RenderWalk
    ) -> tuple[str, RenderedValue]:
        """The structured twin of :meth:`_render_map_entry`: ``ObjectVal`` needs a ``str`` field
        name, so the key is rendered through the flat pipeline (:meth:`_render_map_key`) -- the
        same rendered key text drives both the field name here and the redaction-by-name check,
        rather than each channel re-deriving (and potentially disagreeing on) its own key text."""
        key_name = self._render_map_key(key, walk)
        rendered = (
            StringVal(REDACTED_MARKER)
            if self.redaction_policy.should_redact(key_name)
            else self._render_structured_element(item, walk)
        )
        return key_name, rendered

    def _render_structured_object(self, value: object, walk: _RenderWalk) -> RenderedValue:
        if walk.seen(value):
            return StringVal(_identity_marker(value))
        walk.enter(value)
        try:
            names = _field_names(value)
            fields: dict[str, RenderedValue] = {}
            for name in names[: self.max_object_fields]:
                fields[name] = self._render_structured_field(value, name, walk)
            return ObjectVal(type(value).__name__, fields)
        finally:
            walk.exit(value)

    def _render_structured_field(
        self, value: object, name: str, walk: _RenderWalk
    ) -> RenderedValue:
        annotated = is_field_not_traced(type(value), name)
        if self.redaction_policy.is_redacted(name, annotated=annotated):
            return StringVal(REDACTED_MARKER)
        try:
            return self._render_structured(getattr(value, name), walk)
        except Exception as exc:  # a rogue getter must not break capture
            return StringVal(_error_marker(exc))

    # ------------------------------------------------------------------ #
    # Shared helpers                                                      #
    # ------------------------------------------------------------------ #
    def _render_structured_future(self, value: object, walk: _RenderWalk) -> RenderedValue:
        future: Any = value
        try:
            is_done = future.done()
        except Exception:  # a rogue Future must not break capture
            return StringVal("<failed>")
        if not is_done:
            return StringVal("<pending>")
        try:
            is_cancelled = future.cancelled()
        except Exception:
            return StringVal("<failed>")
        if is_cancelled:
            return StringVal("<cancelled>")
        try:
            return self._render_structured(future.result(), walk)
        except Exception:  # failed dereference renders a marker
            return StringVal("<failed>")

    @staticmethod
    def _is_future(value: object) -> bool:
        return isinstance(value, (concurrent.futures.Future, asyncio.Future))


class _Shape(Enum):
    """How a value that is neither a collection, a future, nor a summary-hook holder renders.

    One decision, consulted by BOTH channels (:meth:`ValueRenderer._render_complex` and
    :meth:`ValueRenderer._render_structured_complex`), so the flat text and the structured export
    cannot drift apart about what a value is allowed to say about itself.
    """

    FIELDS = "fields"
    """Introspected field by field: its declared components, each redactable by name."""

    OWN_STRING = "own-string"
    """Rendered through the value's own string conversion -- the one string conversion rendering
    may call, and only for a type the platform itself defines (see :func:`_is_platform_type`)."""

    OPAQUE = "opaque"
    """Rendered as its type name alone: present in the trace, bounded, and unread."""


def _shape_of(value: object) -> _Shape:
    """Which of the three renderings ``value`` gets -- the rendering rule's decision point.

    A value whose components are DECLARED (a dataclass, an ``attrs`` class, a ``NamedTuple``) is
    introspected by declaration, whatever else it also is. A type the platform defines renders
    through its own string conversion, trusted by ORIGIN (:func:`_is_platform_type`). Anything else
    carrying readable instance state is introspected field by field.

    Everything remaining is a value that carries no state reflection can read -- and that is NOT a
    statement that it has nothing to tell. A ``ctypes.Structure`` subclass keeps its fields in
    C-level descriptors; an extension type can keep them in a C struct with no Python attribute at
    all; an ordinary class can keep its state in a module-level table keyed by identity, or in a
    closure. All of them reflect as fieldless, and all of them can print every field they hold from
    their own ``__str__``/``__repr__`` -- which would reach the trace with nothing but a length cap
    in front of it: past redaction by field name, past the deny-list, past the caps a walked
    composite obeys. So emptiness buys no trust at all: such a value renders as its type name, the
    same shape an undeclared iterable gets (:func:`_bare_iterable_marker`) and for the same reason
    -- the element or the value stays visible, its state stays unread.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _Shape.FIELDS
    if hasattr(type(value), "__attrs_attrs__"):
        return _Shape.FIELDS
    if _is_named_tuple(value):
        return _Shape.FIELDS
    if _is_platform_type(type(value)):
        return _Shape.OWN_STRING
    if _has_instance_state(value):
        return _Shape.FIELDS
    return _Shape.OPAQUE


def _opaque_marker(value: object) -> str:
    """The bounded rendering of a value whose state rendering may not read: its type name alone.

    Never its size: asking for one means calling ``__len__``, which is the value's own behaviour
    -- the very thing this marker exists to avoid running. An undeclared ITERABLE gets its size
    (:func:`_bare_iterable_marker`) because the protocol it declares is what makes a length read
    meaningful there; a value that declares nothing gets its name and nothing more.
    """
    return f"<{type(value).__name__}>"


def _is_trusted_numeric(value: int | float) -> bool:
    """True only for the literal built-in ``int``/``float`` -- never a subclass.

    A security fuzz suite finding (fixed 2026-09-04): ``isinstance(value, (int, float))`` matches
    an ``IntEnum``, a hostile ``Number``-like subclass, or any other wrapper overriding
    ``__str__``, so the numeric fast path uses ``type(value) in ...`` (exact match) instead --
    the same class of bug
    ``_is_named_tuple`` below deliberately does *not* have, since a genuine subclass there still
    carries the base type's real field names.
    """
    return type(value) in _TRUSTED_NUMERIC_TYPES


def _is_named_tuple(value: object) -> bool:
    """Whether ``value`` is a ``NamedTuple`` instance — a ``tuple`` subclass with named fields.

    A plain ``tuple`` has no field names to redact by, so it renders as an anonymous positional
    collection (``_render_collection``). A ``NamedTuple`` is still a ``tuple`` (``isinstance``
    would otherwise route it there too), but its fields carry names a redaction rule can match —
    the same class of bug as a wrapper printing past its payload's redaction, opened one container
    deep instead of stringified whole.
    """
    return isinstance(value, tuple) and hasattr(type(value), "_fields")


_PLATFORM_ANCESTOR_ITER: dict[type, Callable[[Any], Iterator[object]]] = {
    list: list.__iter__,
    tuple: tuple.__iter__,
    set: set.__iter__,
    frozenset: frozenset.__iter__,
}
"""The unbound ``__iter__`` slot of each type in :data:`_COLLECTION_TYPES`, called with the
subclass instance as ``self`` -- the platform ancestor's own iteration, never the attribute
lookup (``iter(value)``/``for x in value``) that would dispatch to a subclass's overridden
``__iter__`` instead."""


def _collection_elements(value: Any) -> list[object]:
    """Reads a collection's elements: the exact platform type's own ``list(value)`` when ``value``
    IS one of :data:`_COLLECTION_TYPES`, unchanged since there is nothing below it to override; a
    user SUBCLASS of one of them instead through that ancestor's own iteration slot (see
    :data:`_PLATFORM_ANCESTOR_ITER`), bypassing whatever the subclass overrode -- the rendering
    rule: rendering reads state, never runs behaviour."""
    exact = type(value)
    if exact in _COLLECTION_TYPES:
        return list(value)
    for base, ancestor_iter in _PLATFORM_ANCESTOR_ITER.items():
        if isinstance(value, base):
            return list(ancestor_iter(value))
    return list(value)  # unreachable given every caller's isinstance(_COLLECTION_TYPES) guard


def _map_items(value: dict[Any, Any]) -> list[tuple[object, object]]:
    """Reads a mapping's entries: ``dict.items()`` directly for an exact ``dict``, or -- for a
    user subclass -- through ``dict``'s own ``items`` slot (``dict.items(value)``, unbound),
    bypassing a subclass's overridden ``items``/``__iter__``. Same rule and reasoning as
    :func:`_collection_elements`."""
    if type(value) is dict:
        return list(value.items())
    return list(dict.items(value))


class _Enumeration(Enum):
    """Whether, and how, a value's elements may be walked: the ONE origin decision of the
    rendering rule, asked once per value by BOTH channels
    (:meth:`ValueRenderer._render_if_enumerable` and
    :meth:`ValueRenderer._render_structured_if_enumerable`) so the flat text and the structured
    export cannot drift apart (B-191; the Java twin is ``ElementOrigin``). Each channel only
    ENCODES the verdict."""

    DECLARED = "declared"
    """The type declares ``__narrative_elements__``: enumerate through the hook (asked first)."""

    COLLECTION = "collection"
    """An exact platform collection, or a user subclass read through the ancestor's own state."""

    MAP = "map"
    """An exact ``dict`` or a user ``dict`` subclass read through ``dict``'s own state."""

    BARE_ITERABLE = "bare-iterable"
    """An ``Iterable`` that is not a ``Collection``: type name and size, never its iterator."""

    NOT_ENUMERABLE = "not-enumerable"
    """Not enumerated here: the caller continues with summary, introspection and leaf text."""


def _enumeration_of(value: object) -> _Enumeration:
    """The verdict for one value -- the single place the enumeration order is decided."""
    if _has_elements_hook(value):
        return _Enumeration.DECLARED
    if isinstance(value, _COLLECTION_TYPES) and not _is_named_tuple(value):
        return _Enumeration.COLLECTION
    if isinstance(value, dict):
        return _Enumeration.MAP
    if isinstance(value, Iterable) and not isinstance(value, Collection):
        return _Enumeration.BARE_ITERABLE
    return _Enumeration.NOT_ENUMERABLE


def _has_elements_hook(value: object) -> bool:
    """Whether ``value``'s type declares the third sanctioned rendering hook (see
    :data:`_ELEMENTS_HOOK`) -- checked on the TYPE, never the instance, so a merely-similarly-
    named instance attribute cannot forge the declaration."""
    return callable(getattr(type(value), _ELEMENTS_HOOK, None))


def _bare_iterable_marker(value: object) -> str:
    """The bounded marker for an ``Iterable`` that is not a full ``Collection`` (see
    :meth:`ValueRenderer._render_if_enumerable`): its type name, plus its size when ``len()`` is
    available and does not raise -- never its elements, and never its ``__iter__``."""
    try:
        size = len(value)  # type: ignore[arg-type]
    except Exception:  # no __len__, or a rogue one -- size is not "free" here
        return f"<{type(value).__name__}>"
    return f"{type(value).__name__} (size {size})"


def _field_names(value: object) -> list[str]:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [f.name for f in dataclasses.fields(value)]
    attrs = getattr(type(value), "__attrs_attrs__", None)
    if attrs is not None:
        return [a.name for a in attrs]
    fields = getattr(type(value), "_fields", None)
    if fields is not None:
        return list(fields)
    if hasattr(value, "__dict__"):
        return list(vars(value))
    return [name for name in _slot_names(type(value)) if hasattr(value, name)]


def _slot_names(cls: type) -> list[str]:
    """Every ``__slots__`` name declared anywhere in ``cls``'s MRO, own class first, with
    ``__dict__``/``__weakref__`` (slot pseudo-entries, never real fields) and duplicates dropped."""
    names: list[str] = []
    for klass in cls.__mro__:
        slots = klass.__dict__.get("__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for slot in slots:
            if slot in ("__dict__", "__weakref__") or slot in names:
                continue
            names.append(slot)
    return names


def read_backing_field(obj: object, name: str) -> object:
    """Reads ``name``'s backing state off ``obj`` -- an instance ``__dict__`` entry or a declared
    ``__slots__`` slot -- never a ``property`` descriptor and never a method call. Returns
    :data:`STATE_MISSING` when no such state exists: a genuinely computed property, a missing
    member, or a zero-arg method with nothing stored under that name.

    The narration-template counterpart of :func:`_field_names`/:func:`_has_instance_state`
    (the rendering rule: rendering/narration reads state, never runs behaviour), used by
    :mod:`narrativetrace.template` and :mod:`narrativetrace.redacted_paths` to resolve a
    ``{obj.prop}`` placeholder and to decide whether one is redacted, without ever invoking
    whatever ``prop`` happens to be.
    """
    if hasattr(obj, "__dict__"):
        instance_dict = vars(obj)
        if name in instance_dict:
            return instance_dict[name]
    if name in _slot_names(type(obj)):
        try:
            return getattr(obj, name)
        except AttributeError:
            return STATE_MISSING
    return STATE_MISSING


def _is_platform_type(cls: type) -> bool:
    """Whether ``cls`` is defined by the platform (the standard library or the interpreter
    itself) rather than the application -- the carve-out that lets a stateful platform value like
    ``pathlib.Path`` or ``uuid.UUID`` keep its own ``str()`` instead of being walked field-by-field
    (see the module docstring).

    Decided by ORIGIN, never by name: a class's ``__module__`` is set to wherever *that class* was
    defined and is not inherited down to subclasses, so a user subclass of a platform type (its
    ``__module__`` is the user's module) and a user class that merely shares a platform type's name
    (its ``__module__`` is never a standard-library top-level package) both correctly fail this
    test -- a name or a prefix comparison would get both wrong. The second branch (no heap-type
    flag) catches a genuine interpreter built-in whose reported ``__module__`` is ``"builtins"``
    all the same, and is what Java's identical carve-out reaches by identity of the *defining class
    loader* rather than a module name -- CPython has no loader for a type the interpreter itself
    allocates, so the heap-type flag is the analogous identity signal here.

    A type that NAMES an origin is judged by that origin alone; the heap-type flag decides only for
    a type that names none. A third-party C extension can perfectly well allocate its types
    statically too, so a bare "not a heap type" test would hand an extension module's own types the
    trust meant for the interpreter's -- and an extension type's fields live in a C struct no
    reflection here can read, which is precisely the value that must not stand behind its own text
    (see :func:`_shape_of`).
    """
    module = getattr(cls, "__module__", None)
    top_level = module.partition(".")[0] if module else None
    if top_level is not None:
        return top_level in sys.stdlib_module_names
    return not (cls.__flags__ & _HEAP_TYPE_FLAG)


def _has_instance_state(value: object) -> bool:
    """Whether ``value`` actually carries at least one populated instance attribute -- a
    non-empty ``__dict__``, or a set ``__slots__`` slot, own or inherited.

    Deliberately about POPULATED state, not merely the storage mechanism's existence: every plain
    Python object without ``__slots__`` carries a ``__dict__`` whether or not anything is ever
    assigned to it, so gating on ``hasattr(value, "__dict__")`` alone would report a field walk as
    worthwhile for a class that has no field to walk.

    Answers only "is there state to introspect", never "is this value safe to let speak for
    itself": a false answer here costs a type-name rendering instead of a field list, never a
    leak. Anything that DOES carry a field is introspected field-by-field even when it also
    overrides ``__str__``/``__repr__`` -- the family invariant that a composite's native
    stringification is never trusted -- and anything that does not is rendered as its type name
    unless its ORIGIN earns it its own string conversion (see :func:`_shape_of`)."""
    if hasattr(value, "__dict__"):
        return bool(vars(value))
    return any(hasattr(value, name) for name in _slot_names(type(value)))


def _error_marker(exc: BaseException) -> str:
    """The typed error marker for a part that failed to render: the exception's own TYPE name,
    never ``str(exc)`` -- a message can carry the very value that failed to render. Used wherever
    a ``@narrative_summary`` method, a custom ``__str__``, or a field getter raises."""
    return f"<error: {type(exc).__name__}>"


def _identity_marker(value: object) -> str:
    return f"<{type(value).__name__}@{id(value):x}>"


def _find_summary_method(cls: type) -> Callable[[object], object] | None:
    for name in dir(cls):
        member = getattr(cls, name, None)
        if callable(member) and getattr(member, _NARRATIVE_SUMMARY_ATTR, False):
            return member  # type: ignore[no-any-return]
    return None
