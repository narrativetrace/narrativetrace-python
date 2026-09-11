# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``trace_object`` — a transparent tracing wrapper over an object's public methods.

The tracing proxy in Python form. Instead of JDK dynamic
proxies, a lightweight wrapper intercepts public callable attributes via ``__getattr__``,
captures parameters by name (via :func:`inspect.signature`), resolves ``@narrated`` / ``@on_error``
templates, renders return values, and records exceptions — delegating to the real object.

Guarantees pinned here (proxy-render §TS-PROXY-6, §TS-PIPE-3):

* **fast path** — an inactive context short-circuits to raw delegation with zero rendering work.
* **fail-safe capture** — a throwing renderer/exit recorder (or capture setup) never masks the
  business result or the business exception, for both sync and ``async`` methods (the TypeScript
  runtime turned a success into a throw — this does not).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from inspect import Parameter, Signature
from typing import Any

from narrativetrace._boundary import PROPAGATED_EXCEPTIONS
from narrativetrace.context import NarrativeContext
from narrativetrace.decorators import MethodMetadata, read_method_metadata, resolve_error_context
from narrativetrace.ids import SpanId
from narrativetrace.redaction import REDACTED_MARKER, RedactionPolicy
from narrativetrace.rendering import ValueRenderer
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.template import resolve as _resolve_template

_DEFAULT_RENDERER = ValueRenderer()


def trace_object[T](
    target: T,
    context: NarrativeContext,
    *,
    class_name: str | None = None,
    renderer: ValueRenderer | None = None,
) -> T:
    """Wraps ``target`` so its public method calls are traced into ``context``.

    Public callables are intercepted; dunder/private attributes and properties delegate raw.
    Nested wrapping is supported. Returns a proxy that is a drop-in for ``target``.
    """
    proxy = _TracedProxy(target, context, class_name, renderer or _DEFAULT_RENDERER)
    return proxy  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class _MethodSpec:
    """Per-method invariants computed once at wrap time.

    ``package_name``, ``return_type``, ``parameter_types`` and ``redacted_params`` are the
    canonical schema's identity fields (the last one, redaction, security-critical rather than
    identity). They come from the declaration, not from the call, so they are read once per
    wrapped method rather than on every invocation -- see :data:`_MethodSpec.redacted_params`.
    """

    meta: MethodMetadata
    sig: Signature | None
    class_name: str
    method_name: str
    renderer: ValueRenderer
    package_name: str | None = None
    return_type: str | None = None
    parameter_types: dict[str, str] = field(default_factory=dict)
    redacted_params: frozenset[str] = field(default_factory=frozenset)
    """Which declared parameter names redact, decided once here rather than once per call.

    Confirmed defect (fixed here): :func:`_build_capture` used to ask only ``name in
    meta.not_traced_params`` -- the explicit ``@not_traced`` decorator -- and never consulted
    :class:`~narrativetrace.redaction.RedactionPolicy` at all, so a parameter named
    ``payment_token`` with no annotation rendered in cleartext. Folded in here instead of
    :class:`~narrativetrace.decorators.MethodMetadata` because the redaction decision needs two
    things ``MethodMetadata`` alone does not carry: the full parameter-name vocabulary (from
    ``sig``/``traced_names``) and the policy in force (``renderer.redaction_policy``, which a
    caller can replace) -- both already live in ``_MethodSpec``, computed once when a method is
    first wrapped (:meth:`_TracedProxy._wrap`) and reused for every subsequent call. Mirrors
    Java's cached ``RedactionPolicy.DEFAULT.isRedacted(name, wasAnnotated)`` widening: the per-call
    cost is one frozenset lookup, not a policy evaluation. Unlike the ``@narrated``/``@on_error``
    template path (a documented narrowness -- see ``template.py``), this honours whichever policy
    the caller's own ``ValueRenderer`` carries -- unioned with, never in place of, the built-in
    ``RedactionPolicy.DEFAULT`` floor (see :func:`_redacted_params`, monotonicity: a mechanism may
    only widen what redacts, never narrow it).
    """


class _TracedProxy:
    def __init__(
        self,
        target: object,
        context: NarrativeContext,
        class_name: str | None,
        renderer: ValueRenderer,
    ) -> None:
        object.__setattr__(self, "_nt_target", target)
        object.__setattr__(self, "_nt_context", context)
        object.__setattr__(self, "_nt_class_name", class_name or type(target).__name__)
        # Read off the real type even when the caller renamed the class: `class_name` is a display
        # choice, the package is identity, and mixing the two would misattribute the call.
        object.__setattr__(self, "_nt_package_name", getattr(type(target), "__module__", None))
        object.__setattr__(self, "_nt_renderer", renderer)
        object.__setattr__(self, "_nt_cache", {})

    def __getattr__(self, name: str) -> Any:
        target = object.__getattribute__(self, "_nt_target")
        attr = getattr(target, name)
        if name.startswith("_"):
            return attr
        static = inspect.getattr_static(type(target), name, None)
        if isinstance(static, property):
            return attr
        if not callable(attr):
            return attr
        cache: dict[str, Callable[..., Any]] = object.__getattribute__(self, "_nt_cache")
        wrapped = cache.get(name)
        if wrapped is None:
            wrapped = self._wrap(attr)
            cache[name] = wrapped
        return wrapped

    def _method_spec(self, bound_method: Callable[..., Any]) -> _MethodSpec:
        renderer: ValueRenderer = object.__getattribute__(self, "_nt_renderer")
        class_name: str = object.__getattribute__(self, "_nt_class_name")
        package_name: str | None = object.__getattribute__(self, "_nt_package_name")
        func = getattr(bound_method, "__func__", bound_method)
        try:
            sig: Signature | None = inspect.signature(bound_method)
        except (ValueError, TypeError):
            sig = None
        meta = read_method_metadata(func)
        return _MethodSpec(
            meta,
            sig,
            class_name,
            getattr(func, "__name__", "call"),
            renderer,
            package_name,
            _return_type_of(sig),
            _parameter_types_of(sig),
            _redacted_params(sig, meta, renderer.redaction_policy),
        )

    def _wrap(self, bound_method: Callable[..., Any]) -> Callable[..., Any]:
        context: NarrativeContext = object.__getattribute__(self, "_nt_context")
        spec = self._method_spec(bound_method)

        @functools.wraps(getattr(bound_method, "__func__", bound_method))
        def wrapper(*args: object, **kwargs: object) -> Any:
            if not context.is_active():
                return bound_method(*args, **kwargs)
            try:
                signature, value_map = _build_capture(
                    spec, args, kwargs, context.captures_parameter_values()
                )
                span_id = context.enter_method(signature)
            except PROPAGATED_EXCEPTIONS:
                raise
            except BaseException:  # capture setup must never crash the business call
                return bound_method(*args, **kwargs)
            try:
                result = _invoke(context, span_id, bound_method, args, kwargs)
            except BaseException as exc:
                _safe_exit_exception(context, spec.meta, value_map, exc, span_id)
                raise
            if isinstance(result, Awaitable):
                return _run_deferred(context, result, span_id, spec, value_map)
            _safe_exit_return(context, result, span_id, spec.renderer)
            return result

        return wrapper


def _type_name(annotation: object) -> str | None:
    """Formats one annotation as the canonical schema's declared-type string.

    A class renders fully qualified (``builtins.str``, ``acme.billing.Invoice``), matching Java's
    ``Class.getTypeName()`` — a bare ``str`` would not distinguish two same-named classes, which is
    the whole reason the field exists. Everything else renders as written: a generic alias
    (``list[int]``), a union (``int | None``), or a PEP 563 string annotation left unevaluated.

    **Python divergence.** Under ``from __future__ import annotations`` every annotation *is* the
    source text, so the same method reports ``str`` there and ``builtins.str`` in a module without
    that import. Recording what the source declares is deliberate: resolving a string annotation
    means evaluating it, which can import modules and raise ``NameError`` on a forward reference —
    unacceptable on a path whose only job is to describe a call.
    """
    if annotation is Parameter.empty or annotation is Signature.empty:
        return None
    if annotation is None:
        return "None"  # Python's `-> None`, the analogue of Java's `void`
    if isinstance(annotation, str):
        return annotation
    if isinstance(annotation, type):
        return f"{annotation.__module__}.{annotation.__qualname__}"
    return str(annotation)


def _return_type_of(sig: Signature | None) -> str | None:
    return None if sig is None else _type_name(sig.return_annotation)


def _parameter_types_of(sig: Signature | None) -> dict[str, str]:
    """Declared parameter types by name, omitting the unannotated ones."""
    if sig is None:
        return {}
    named = ((name, _type_name(p.annotation)) for name, p in sig.parameters.items())
    return {name: declared for name, declared in named if declared is not None}


def _redacted_params(
    sig: Signature | None, meta: MethodMetadata, redaction_policy: RedactionPolicy
) -> frozenset[str]:
    """Every declared parameter name that must redact: an explicit ``@not_traced`` annotation, or
    the always-on name-based deny-list, decided once per method (see
    :data:`_MethodSpec.redacted_params`).

    The name vocabulary is ``traced_names`` (the ``@traced`` override for signatures ``inspect``
    cannot bind, e.g. bare ``*args``) when supplied, otherwise every name ``inspect.signature``
    reports -- which, for a bound method, already excludes ``self``, so ``self`` can never appear
    in ``sig.parameters`` and never reaches ``redaction_policy`` here.

    **Monotonicity floor (owner ruling).** ``RedactionPolicy.DEFAULT`` is unioned in
    unconditionally alongside ``redaction_policy`` -- a caller's policy may only ADD to what
    redacts here, never replace the built-in floor. ``RedactionPolicy.of_patterns(...)`` replaces
    a policy's vocabulary entirely rather than extending it, and reaches this function directly
    through the public ``ValueRenderer(redaction_policy=...)`` / ``trace_object(...,
    renderer=...)`` seam; without this union, a caller who narrows their own vocabulary (drops
    ``password``, say) would redact less at this axis than the built-in default -- a real,
    reachable weakening, not a hypothetical one. Value-shape masking is a separate axis
    (``should_redact_value``, checked later inside ``ValueRenderer`` when a value *is* rendered)
    and is untouched here: this floor is about the name-based deny-list only.
    """
    names = meta.traced_names or (tuple(sig.parameters) if sig is not None else ())
    return frozenset(
        name
        for name in names
        if redaction_policy.is_redacted(name, annotated=name in meta.not_traced_params)
        or RedactionPolicy.DEFAULT.should_redact(name)
    )


def _invoke(
    context: NarrativeContext,
    span_id: SpanId | None,
    bound_method: Callable[..., Any],
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object:
    if span_id is None:
        return bound_method(*args, **kwargs)
    return context.run_scoped(span_id, lambda: bound_method(*args, **kwargs))


def _build_capture(
    spec: _MethodSpec, args: tuple[object, ...], kwargs: dict[str, object], capture_values: bool
) -> tuple[MethodSignature, dict[str, object]]:
    meta = spec.meta
    items = _bound_items(spec.sig, args, kwargs, meta.traced_names)
    captures: list[ParameterCapture] = []
    value_map: dict[str, object] = {}
    for name, value in items:
        redacted = name in spec.redacted_params
        value_map[name] = REDACTED_MARKER if redacted else value
        declared = spec.parameter_types.get(name)
        captures.append(
            _capture_one(name, value, redacted, capture_values, spec.renderer, declared)
        )
    narration = (
        _resolve_template(meta.narrated_template, value_map)
        if meta.narrated_template is not None
        else None
    )
    signature = MethodSignature(
        spec.class_name,
        spec.method_name,
        captures,
        narration,
        None,
        meta.narrated_template,
        spec.package_name,
        spec.return_type,
    )
    return signature, value_map


def _capture_one(
    name: str,
    value: object,
    redacted: bool,
    capture_values: bool,
    renderer: ValueRenderer,
    declared_type: str | None,
) -> ParameterCapture:
    """Builds one parameter's capture. ``redacted`` here is the NAME axis only (the deny-list/
    ``@not_traced`` decision already made in :data:`_MethodSpec.redacted_params`) -- when it
    fires, ``value`` is never rendered at all, the short-circuit :func:`~narrativetrace.rendering.
    ValueRenderer.render_for_capture` documents relying on. Otherwise the VALUE-SHAPE axis
    (:meth:`~narrativetrace.rendering.ValueRenderer.render_for_capture`'s own boolean, decided at
    the exact point a whole scalar value is replaced by the marker) becomes the capture's
    ``redacted`` flag, so a shape-caught parameter (a JWT, a Luhn PAN, ...) is flagged the same as
    a name-caught one -- see :data:`~narrativetrace.signature.ParameterCapture.redacted`.
    """
    if redacted:
        return ParameterCapture(name, REDACTED_MARKER, True, None, declared_type)
    if not capture_values:
        return ParameterCapture(name, "", False, None, declared_type)
    rendered, structured, shape_redacted = renderer.render_for_capture(value)
    return ParameterCapture(name, rendered, shape_redacted, structured, declared_type)


def _bound_items(
    sig: Signature | None,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    traced_names: tuple[str, ...],
) -> list[tuple[str, object]]:
    if traced_names:
        return list(zip(traced_names, args, strict=False))
    if sig is None:
        return []
    try:
        bound = sig.bind(*args, **kwargs)
    except TypeError:
        return []
    bound.apply_defaults()
    return list(bound.arguments.items())


def _safe_exit_return(
    context: NarrativeContext, result: object, span_id: SpanId | None, renderer: ValueRenderer
) -> None:
    try:
        rendered = renderer.render(result)
        structured = renderer.render_structured(result)
        context.exit_method_with_return(rendered, structured, span_id)
    except PROPAGATED_EXCEPTIONS:
        raise
    except BaseException:  # observability failure must never mask the business result
        try:
            context.exit_method_with_return(None, None, span_id)
        except PROPAGATED_EXCEPTIONS:
            raise
        except BaseException:
            pass


def _safe_exit_exception(
    context: NarrativeContext,
    meta: MethodMetadata,
    value_map: dict[str, object],
    exception: BaseException,
    span_id: SpanId | None,
) -> None:
    try:
        error_context = (
            resolve_error_context(meta.on_errors, exception, value_map) if meta.on_errors else None
        )
        context.exit_method_with_exception(exception, error_context, span_id)
    except PROPAGATED_EXCEPTIONS:
        raise
    except BaseException:  # exit recording must never mask the business exception
        pass


async def _run_deferred(
    context: NarrativeContext,
    awaitable: Awaitable[Any],
    span_id: SpanId | None,
    spec: _MethodSpec,
    value_map: dict[str, object],
) -> Any:
    if span_id is not None:
        context.detach_frame(span_id)
    previous = context.begin_scope(span_id) if span_id is not None else None
    try:
        result = await awaitable
    except asyncio.CancelledError:
        # A cancelled member leaves the frame incomplete (no exit recorded) — plan PY7.4.
        raise
    except BaseException as exc:
        _safe_exit_exception(context, spec.meta, value_map, exc, span_id)
        raise
    finally:
        if span_id is not None:
            context.end_scope(previous)
    _safe_exit_return(context, result, span_id, spec.renderer)
    return result
