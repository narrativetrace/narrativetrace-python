# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Parser and resolver for ``@narrated`` / ``@on_error`` annotation templates.

``TemplateParser``. Substitutes ``{param}`` (unquoted ``str(value)``) and
``{obj.prop}`` (a backing-field STATE read, never a property/accessor invocation — see
:class:`_PropertyPlaceholder`) against a value map built from raw arguments. Unresolved
placeholders are preserved literally instead of raising, so callers can surface warnings (PY8)
rather than crash rendering.

Substitution goes through ``_render_value``: text always renders through
:meth:`~narrativetrace.rendering.ValueRenderer.render_narration_text` (value-shape redaction,
control sanitising, the string cap — minus a captured string's quotation marks); a non-text
scalar (``bool``/the platform's own numeric leaves/``Enum``) renders via its own ``str()`` when
trusted (the exact built-in ``bool``/``int``/``float``/``complex``, matched by class, never a
subclass — a numeric subclass is a composite, and reaches
:class:`~narrativetrace.rendering.ValueRenderer` below like any other; fixed 2026-09-19, the
``number-subclass-tostring-door`` row), control-sanitised when not (an ``Enum`` member, whose
overridden ``__str__`` cannot be trusted), degrading to the ``<TypeName>`` marker when ``str()``
itself misbehaves; anything else always renders through
:class:`~narrativetrace.rendering.ValueRenderer`, the one place redaction is decided, whether or
not the placeholder names a path into the value. A bare ``{key}`` placeholder additionally asks
the redaction deny-list about the key itself — the key is the parameter name, the same input
the path form feeds it (both 2026-09-04, family security fix).

A path reaching a redacted member resolves to ``[REDACTED]`` instead — see
:func:`narrativetrace.redacted_paths.redacts`, called before resolution. Naming a path never
weakens the rules that apply to the value directly; to narrate the value, remove ``@not_traced``
from the member, and that removal is the deliberate, reviewable decision (owner decision
2026-08-31).

**Whole-object placeholders never fall back to the value's own ``str()``/``repr()``**: a
``{card}`` placeholder names the object rather than a path into it, and the object's own
``__str__``/dataclass-generated ``repr`` knows nothing about ``@not_traced`` — routing it through
``ValueRenderer`` unconditionally is what keeps a whole-object placeholder as safe as the
``{card.cvv}`` path form (a 2026-09-02 fix: checking the safe rendering for the redaction
marker and falling back to ``toString()`` when absent is unsound, because the marker is
equally absent when the renderer truncated the value at a field/collection/depth cap without
ever reaching the hidden member).

**Known narrowness, recorded not fixed**: the redaction check always uses
:data:`~narrativetrace.redaction.RedactionPolicy.DEFAULT`, because :func:`resolve` is a free
function and nothing threads a custom policy into it. Today that is exactly the policy in force —
:func:`~narrativetrace.trace_object.trace_object` accepts a custom ``renderer`` but never passes
its ``redaction_policy`` down to template resolution either — so a custom
``RedactionPolicy.of_patterns(...)`` is honoured by value rendering and not by templates. Whoever
threads a configurable policy through capture owes the same seam here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from narrativetrace.escape import control_sanitize
from narrativetrace.redacted_paths import redacts
from narrativetrace.redaction import REDACTED_MARKER, RedactionPolicy
from narrativetrace.rendering import (
    STATE_MISSING,
    ValueRenderer,
    read_backing_field,
    rendering_scope,
)

_SAFE = ValueRenderer()
_TRUSTED_BUILTIN_SCALAR_TYPES = (bool, int, float, complex)

_PLACEHOLDER = re.compile(r"\{([^}]+)\}")


class _Segment:
    __slots__ = ()

    def resolve(self, values: Mapping[str, object]) -> str:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class _Literal(_Segment):
    text: str

    def resolve(self, values: Mapping[str, object]) -> str:
        return self.text


@dataclass(frozen=True, slots=True)
class _SimplePlaceholder(_Segment):
    """A placeholder naming a value directly — ``{password}``, ``{token}``, ``{card}``.

    @llmNote The key *is* the parameter's name here: the value map is keyed by parameter name,
    so ``{password}`` names the parameter ``password``. That makes the deny-list applicable to
    exactly the same input :func:`~narrativetrace.redacted_paths.redacts` feeds it for a path
    segment, and it is asked the same way — ``RedactionPolicy.is_redacted`` — so one rule answers
    both productions of the grammar. Before 2026-09-04 (family security fix) this production
    asked nothing at all, and ``@narrated("login {password}")`` printed the password that
    ``{user.password}`` beside it answered ``[REDACTED]`` for.

    @edgeCase The name is asked only once a value exists. A placeholder naming no parameter
    stays literal, redacted-sounding or not: nothing can leak through a name that resolves to
    nothing, and answering ``[REDACTED]`` there would swallow the unresolved-placeholder
    warning (PY8) that catches the typo.
    """

    key: str

    def resolve(self, values: Mapping[str, object]) -> str:
        value = values.get(self.key)
        if value is None:
            return f"{{{self.key}}}"
        if RedactionPolicy.DEFAULT.is_redacted(self.key, annotated=False):
            return REDACTED_MARKER
        return _render_value(value)


@dataclass(frozen=True, slots=True)
class _PropertyPlaceholder(_Segment):
    """A placeholder naming a member of a value — ``{order.total}``, ``{card.cvv}``.

    @llmNote Resolved from STATE, never behaviour (the rendering rule: rendering reads state,
    never runs behaviour): the member's own backing field
    (:func:`~narrativetrace.rendering.read_backing_field`) — an instance ``__dict__`` entry or a
    declared ``__slots__`` slot — exactly once, under :func:`~narrativetrace.rendering
    .rendering_scope` so a woven accessor reached from further inside a value's own rendering
    opens no phantom span. A genuinely computed ``@property`` or a zero-arg method has no such
    state, so it is never invoked — the placeholder stays literal instead of running it, the same
    way a missing member does. Before this fix, resolution invoked the named accessor directly
    (and the redaction check above invoked it a second time, to decide whether to), so a property
    with a side effect ran twice per placeholder resolved.
    """

    object_key: str
    property_name: str

    def resolve(self, values: Mapping[str, object]) -> str:
        literal = f"{{{self.object_key}.{self.property_name}}}"
        obj = values.get(self.object_key)
        if obj is None:
            return literal
        if redacts(obj, self.property_name, RedactionPolicy.DEFAULT):
            return REDACTED_MARKER
        with rendering_scope():
            value = read_backing_field(obj, self.property_name)
        if value is STATE_MISSING or value is None:
            return literal
        return _render_value(value)


def _is_scalar(value: object) -> bool:
    """Whether ``value`` is its own best narration and cannot hide a redacted member.

    The platform's own boolean/numeric/complex leaves and enum constants are scalar; everything
    else — a dataclass, a plain object, a collection — can carry a ``@not_traced`` field or a
    deny-listed name somewhere inside it, so it must be rendered by
    :class:`~narrativetrace.rendering.ValueRenderer` rather than its own ``str()``/``repr()``.

    @edgeCase ``str`` was on this list until 2026-09-04 (family security fix) and is deliberately
    not any more: text is the one scalar whose *content* can be a credential, so it is answered
    by :meth:`~narrativetrace.rendering.ValueRenderer.render_narration_text` in
    :func:`_render_value` rather than by its own ``str()``.

    @edgeCase A numeric/complex value is a scalar here only for the exact built-in type (mirrors
    :class:`~narrativetrace.rendering.ValueRenderer`'s identical gate, one branch over): an
    ``int``/``float``/``complex`` SUBCLASS can hold anything, including a deny-listed field its
    ``__str__`` prints, and a narration template is rendering like any other — so it goes to
    :class:`~narrativetrace.rendering.ValueRenderer` and is walked, exactly as it is when the same
    value is captured as an argument (fixed 2026-09-19, the ``number-subclass-tostring-door`` row:
    ``isinstance``-based dispatch here used to trust ANY numeric subclass, sanitizing rather than
    withholding a deny-listed field printed by its own text).
    """
    return _is_trusted_builtin_scalar(value) or isinstance(value, Enum)


def _render_value(value: object) -> str:
    """Renders a resolved value for substitution, through the one renderer that knows what is
    hidden.

    INTENT: narration must never break the call it narrates, and must never out-narrate the
    redaction policy. A captured value is arbitrary application data — a lazy proxy over a closed
    session, a half-built entity, a recursive structure — so every non-scalar goes to
    :class:`~narrativetrace.rendering.ValueRenderer`, which is total, bounded, and the single
    place redaction is decided.

    @edgeCase There is deliberately no fallback to the value's own ``str()``/``repr()`` for a
    non-scalar, and no "does the safe rendering contain the redaction marker" check gating that
    fallback either. That check is unsound: the marker is equally absent when the renderer never
    saw the whole value — truncated at the field/collection cap, cut at ``ValueRenderer.MAX_DEPTH``,
    stopped at a cycle — as when there is genuinely nothing to hide. "No marker" means "nothing is
    hidden" and "the renderer did not look" alike, and only routing every non-scalar through
    ``ValueRenderer`` unconditionally answers the two differently (fixed 2026-09-02, found by
    property-based fuzzing).

    @llmNote Text is not a fast path. A ``str`` carries the one shape the value axis exists
    for — a bearer token, a card number, a ``Set-Cookie`` string arriving under a name nothing
    suspects — so it goes to :meth:`~narrativetrace.rendering.ValueRenderer.render_narration_text`,
    which applies exactly what the renderer applies to a captured string minus the quotation
    marks a narration must not carry. It used to take the scalar shortcut below, which meant a
    JWT rendered ``[REDACTED]`` as an argument and in full through ``@narrated("issued {token}")``
    (fixed 2026-09-04, family security fix).
    """
    if isinstance(value, str):
        return _SAFE.render_narration_text(value)
    return _scalar_text(value) if _is_scalar(value) else _SAFE.render(value)


def _is_trusted_builtin_scalar(value: object) -> bool:
    """True only for the literal built-in ``bool``/``int``/``float``/``complex`` -- never a
    subclass.

    As of 2026-09-04: a plain ``Enum`` overrides ``__str__`` and is a scalar too
    (``_is_scalar``'s second, separate check), but is never a subclass OF one of these four types,
    so an exact-type match here is enough to keep it out. As of 2026-09-19: an ``IntEnum`` or a
    hostile numeric subclass IS a subclass of one of these four (``int``), which is exactly why
    ``_is_scalar`` no longer asks ``isinstance`` of this tuple either — both call sites ask this
    exact-type gate instead, so neither can drift onto trusting a subclass's overridden
    ``__str__``.
    """
    return type(value) in _TRUSTED_BUILTIN_SCALAR_TYPES


def _scalar_text(value: object) -> str:
    """A scalar's own text, or its type marker when ``str()`` raises or answers non-``str``.

    @llmNote Degrades to the same ``<TypeName>`` marker ``ValueRenderer._render_with_str`` uses
    for this hazard: the two renderers must agree, because a value safe to capture must also be
    safe to narrate. ``except Exception`` is the right width here — ``RecursionError`` (a deeply
    recursive ``__str__``, Java's ``StackOverflowError``) and ``TypeError`` (a ``__str__``
    returning a non-``str``) are both ``Exception`` subclasses, while ``BaseException`` would
    swallow ``KeyboardInterrupt``.

    A trusted built-in scalar renders as its own ``str()``; an ``Enum`` member has no such
    guarantee for its overridden ``__str__``, so it is control-sanitised here instead (mirrors
    ``ValueRenderer``'s identical enum fast path). A numeric subclass never reaches here at all as
    of 2026-09-19 — ``_is_scalar`` is where it is turned away, to :func:`_render_value`'s
    :class:`~narrativetrace.rendering.ValueRenderer` fallback, the composite it actually is. Text
    never reaches here either — ``_render_value`` routes every ``str`` to
    :meth:`~narrativetrace.rendering.ValueRenderer.render_narration_text` first.
    """
    try:
        text = str(value)
    except Exception:  # a rogue __str__ may raise anything
        return f"<{type(value).__name__}>"
    if _is_trusted_builtin_scalar(value):
        return text
    return control_sanitize(text)  # an Enum constant's own text, the last branch that reads it


_MAX_CACHED_TEMPLATES = 512
"""Bounds the parsed-template cache below. Templates are ordinarily fixed at
``@narrated``/``@on_error`` decoration time (finite by construction, one per call site), but
nothing enforces that at this function's boundary, so the cache is bounded rather than trusted to
stay small."""


def _parse_placeholder(key: str) -> _Segment:
    dot = key.find(".")
    if dot >= 0:
        return _PropertyPlaceholder(key[:dot], key[dot + 1 :])
    return _SimplePlaceholder(key)


@lru_cache(maxsize=_MAX_CACHED_TEMPLATES)
def _parse(template: str) -> list[_Segment]:
    segments: list[_Segment] = []
    last_end = 0
    for match in _PLACEHOLDER.finditer(template):
        if match.start() > last_end:
            segments.append(_Literal(template[last_end : match.start()]))
        segments.append(_parse_placeholder(match.group(1)))
        last_end = match.end()
    if last_end < len(template):
        segments.append(_Literal(template[last_end:]))
    return segments


def resolve(template: str, values: Mapping[str, object]) -> str:
    """Resolves ``template`` against ``values``, preserving unresolved placeholders literally."""
    return "".join(segment.resolve(values) for segment in _parse(template))


def find_unresolved(resolved: str | None) -> list[str]:
    """Returns the placeholder keys still present in a resolved string (for PY8 warnings)."""
    if resolved is None:
        return []
    return [match.group(1) for match in _PLACEHOLDER.finditer(resolved)]
