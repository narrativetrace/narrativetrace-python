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
regardless of a custom ``__str__``/``__repr__`` override -- only a genuine leaf (no instance state
at all: a number, a string, a payload-free enum, ...) still trusts ``str()``. Before this fix,
``_introspectable`` asked only "does this type override ``__str__``", so a hand-written
``__str__`` that interpolated a sensitive field (or a nested object's own hostile ``__str__``) ran
completely unmediated -- past redact-by-name, the deny-list, depth caps, everything. Dict KEYS are
rendered through this same pipeline (redaction-by-name and introspection both apply to a key, not
just its value), rather than a bare ``str(key)`` that bypassed every guard unconditionally. When a
``@narrative_summary`` method, a custom ``__str__``, or an object's own field getter raises, that
one part renders ``<error: <TypeName>>`` -- the exception's own type name, never ``str(exc)``
(a message can carry the very value that failed to render).

**Platform-defined types are trusted for native stringification even though they carry state**
*(since 0.1.2, unreleased)*: the 2026-09-11 fix above is correct for application types but too
broad for the standard library's own value types -- ``pathlib.Path``, ``datetime``,
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

Depth limiting (a security fuzz suite finding, mirrors Java's ``RenderWalk``): an identity-based
cycle guard answers "have I been here before", never "how deep am I" -- a linear chain of distinct
objects never repeats an identity, so the guard alone let a 10,000-node chain recurse Python's
interpreter past its stack limit, escaping as an uncaught ``RecursionError``. ``MAX_DEPTH`` (32,
matching the Java fix) is the fourth cap beside the 200-character string limit, the 5-element
collection limit and the 5-field object limit; a value beyond it renders as ``<max-depth>`` --
unreached, so a redacted component past the cap is never printed, not even partially.

``NamedTuple`` is introspected by field name rather than rendered as an anonymous positional
collection (the template-resolution family, Java's wrapper-``toString()`` bug class applied to a
Python-only shape): being a ``tuple`` subclass, it would otherwise reach ``_render_collection``
first and print every field's raw value with no redaction check at all, since a collection
element carries no name to redact by.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import inspect
import sys
from collections.abc import Callable
from enum import Enum
from typing import Any, ClassVar

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

_COLLECTION_TYPES = (list, tuple, set, frozenset)

_TOO_DEEP = "<max-depth>"

_TRUSTED_NUMERIC_TYPES = (int, float)

_HEAP_TYPE_FLAG = 1 << 9
"""``Py_TPFLAGS_HEAPTYPE``: set on every ordinary Python class, clear only on a type allocated
statically inside the interpreter (``int``, ``str``, ``datetime.datetime``, ...). A stable CPython
ABI flag, not a private implementation detail."""


class _RenderWalk:
    """One render call's recursion state: identity ancestry plus remaining depth budget.

    ``RenderWalk``. The two answer different questions -- "have I been here before"
    (cycles) and "how deep am I" (stack safety) -- but both unwind in the same ``finally``, so one
    object owns both rather than threading two parameters through every recursive method.
    """

    __slots__ = ("_ancestors", "_depth")

    def __init__(self) -> None:
        self._ancestors: set[int] = set()
        self._depth = 0

    def seen(self, value: object) -> bool:
        """Whether ``value`` is already an ancestor on the current path (a cycle)."""
        return id(value) in self._ancestors

    def enter(self, value: object) -> None:
        """Marks ``value`` as an ancestor of whatever is rendered next."""
        self._ancestors.add(id(value))

    def exit(self, value: object) -> None:
        """Un-marks ``value`` once its subtree has finished rendering."""
        self._ancestors.discard(id(value))

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
        try:
            return self._render(value, _RenderWalk())
        except Exception:  # the renderer is total: nothing a value does may escape capture
            return f"<{type(value).__name__}>"

    def _render(self, value: object, walk: _RenderWalk) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, str):
            return self._render_string(value)
        if isinstance(value, (int, float)):
            return self._render_number(value)
        if isinstance(value, Enum):
            return self._render_with_str(value)  # no trusted built-in Enum: __str__ is overridable
        if not walk.descend():
            return _TOO_DEEP
        try:
            return self._render_complex(value, walk)
        finally:
            walk.ascend()

    def _render_structured_string(self, value: str) -> RenderedValue:
        if self.redaction_policy.should_redact_value(value):
            return StringVal(REDACTED_MARKER)
        return StringVal(value)

    def _render_structured_int(self, value: int) -> RenderedValue:
        if _is_trusted_numeric(value):
            return IntVal(value)
        return StringVal(self._render_with_str(value))  # a Number subclass may forge control chars

    def _render_structured_float(self, value: float) -> RenderedValue:
        if _is_trusted_numeric(value):
            return FloatVal(value)
        return StringVal(self._render_with_str(value))  # a Number subclass may forge control chars

    def _render_number(self, value: int | float) -> str:
        if _is_trusted_numeric(value):
            return str(value)
        return self._render_with_str(value)  # a Number subclass may forge control chars

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
        if isinstance(value, _COLLECTION_TYPES) and not _is_named_tuple(value):
            return self._render_collection(value, walk)
        if isinstance(value, dict):
            return self._render_map(value, walk)
        summary = self._render_summary(value)
        if summary is not None:
            return summary
        if self._introspectable(value):
            return self._render_introspected(value, walk)
        return self._render_with_str(value)

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
            items = list(value)
        except Exception:  # a rogue iterator must not break capture
            return f"<{type(value).__name__}>"
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
            items = list(value.items())
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

    def _render_summary(self, value: object) -> str | None:
        method = _find_summary_method(type(value))
        if method is None:
            return None
        try:
            return str(method(value))
        except Exception as exc:  # a broken summary is an error, not a silent fallback
            return _error_marker(exc)

    # ------------------------------------------------------------------ #
    # Structured rendering                                                #
    # ------------------------------------------------------------------ #
    def render_structured(self, value: object) -> RenderedValue:
        """Renders ``value`` preserving its Python type as a :class:`RenderedValue`."""
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
        try:
            if isinstance(value, str):
                shape_redacted = self.redaction_policy.should_redact_value(value)
                if shape_redacted:
                    return REDACTED_MARKER, StringVal(REDACTED_MARKER), True
                return self._render_string_body(value), StringVal(value), False
            return self.render(value), self.render_structured(value), False
        except Exception:  # the renderer is total: nothing a value does may escape capture
            marker = f"<{type(value).__name__}>"
            return marker, StringVal(marker), False

    def _render_structured(self, value: object, walk: _RenderWalk) -> RenderedValue:
        if value is None:
            return NullVal()
        if isinstance(value, bool):
            return BoolVal(value)
        if isinstance(value, str):
            return self._render_structured_string(value)
        if isinstance(value, int):
            return self._render_structured_int(value)
        if isinstance(value, float):
            return self._render_structured_float(value)
        if isinstance(value, Enum):
            return StringVal(self._render_with_str(value))
        if not walk.descend():
            return StringVal(_TOO_DEEP)
        try:
            return self._render_structured_complex(value, walk)
        finally:
            walk.ascend()

    def _render_structured_complex(self, value: object, walk: _RenderWalk) -> RenderedValue:
        if self._is_future(value):
            return self._render_structured_future(value, walk)
        if inspect.isawaitable(value):
            return StringVal("<pending>")
        if isinstance(value, _COLLECTION_TYPES) and not _is_named_tuple(value):
            return self._render_structured_collection(value, walk)
        if isinstance(value, dict):
            return self._render_structured_map(value, walk)
        summary = self._render_summary(value)
        if summary is not None:
            return StringVal(summary)
        if self._introspectable(value):
            return self._render_structured_object(value, walk)
        return StringVal(self._render_with_str(value))

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
            items = list(value)[: self.max_collection_items]
        except Exception:  # a rogue iterator must not break capture
            return StringVal(f"<{type(value).__name__}>")
        return ListVal([self._render_structured_element(item, walk) for item in items])

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
            items = list(value.items())
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

    @staticmethod
    def _introspectable(value: object) -> bool:
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return True
        if hasattr(type(value), "__attrs_attrs__"):
            return True
        if _is_named_tuple(value):
            return True
        if _is_platform_type(type(value)):
            return False
        return _has_instance_state(value)


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


def _is_platform_type(cls: type) -> bool:
    """Whether ``cls`` is defined by the platform (the standard library or the interpreter
    itself) rather than the application -- the carve-out that lets a stateful platform value like
    ``pathlib.Path`` or ``uuid.UUID`` keep its own ``str()`` instead of being walked field-by-field
    (owner ruling, 2026-09-12; see the module docstring).

    Decided by ORIGIN, never by name: a class's ``__module__`` is set to wherever *that class* was
    defined and is not inherited down to subclasses, so a user subclass of a platform type (its
    ``__module__`` is the user's module) and a user class that merely shares a platform type's name
    (its ``__module__`` is never a standard-library top-level package) both correctly fail this
    test -- a name or a prefix comparison would get both wrong. The second branch (no heap-type
    flag) catches a genuine interpreter built-in whose reported ``__module__`` is ``"builtins"``
    all the same, and is what Java's identical carve-out reaches by identity of the *defining class
    loader* rather than a module name -- CPython has no loader for a type the interpreter itself
    allocates, so the heap-type flag is the analogous identity signal here.
    """
    module = getattr(cls, "__module__", None)
    top_level = module.partition(".")[0] if module else None
    if top_level is not None and top_level in sys.stdlib_module_names:
        return True
    return not (cls.__flags__ & _HEAP_TYPE_FLAG)


def _has_instance_state(value: object) -> bool:
    """Whether ``value`` actually carries at least one populated instance attribute -- a
    non-empty ``__dict__``, or a set ``__slots__`` slot, own or inherited.

    Deliberately about POPULATED state, not merely the storage mechanism's existence: every plain
    Python object without ``__slots__`` carries a ``__dict__`` whether or not anything is ever
    assigned to it, so gating on ``hasattr(value, "__dict__")`` alone would also flag a genuinely
    stateless class -- a null object, a singleton, a hand-authored formatter with nothing to leak
    -- whose curated ``__str__`` is not a security concern because there is no field behind it to
    bypass. A leaf like a plain ``int``, ``str``, or a payload-free ``Enum`` member has no instance
    state either way; anything that DOES carry a field is introspected field-by-field even when it
    also overrides ``__str__``/``__repr__`` -- the family invariant that a composite's native
    stringification is never trusted (2026-09-11)."""
    if hasattr(value, "__dict__"):
        return bool(vars(value))
    return any(hasattr(value, name) for name in _slot_names(type(value)))


def _error_marker(exc: BaseException) -> str:
    """The typed error marker for a part that failed to render: the exception's own TYPE name,
    never ``str(exc)`` -- a message can carry the very value that failed to render (owner ruling,
    2026-09-11). Used wherever a ``@narrative_summary`` method, a custom ``__str__``, or a field
    getter raises."""
    return f"<error: {type(exc).__name__}>"


def _identity_marker(value: object) -> str:
    return f"<{type(value).__name__}@{id(value):x}>"


def _find_summary_method(cls: type) -> Callable[[object], object] | None:
    for name in dir(cls):
        member = getattr(cls, name, None)
        if callable(member) and getattr(member, _NARRATIVE_SUMMARY_ATTR, False):
            return member  # type: ignore[no-any-return]
    return None
