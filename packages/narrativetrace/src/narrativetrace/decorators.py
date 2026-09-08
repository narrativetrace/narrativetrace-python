# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Method/parameter decorators driving traced narration and redaction.

The Java annotations ``@Narrated``, ``@OnError``, ``@NotTraced`` (parameter form), and the
TS/.NET ``@Traced`` name-override. Decorators attach metadata to the function object; the
:mod:`narrativetrace.trace_object` wrapper reads it at call time.

* ``@narrated("Greeting {name}")`` — a narration template resolved against arguments.
* ``@on_error(ExcType, "template")`` — stackable; resolved against the raised type at exit,
  most-specific-wins. Bare ``@on_error("template")`` is a catch-all over ``Exception``.
* ``@not_traced("password", "cvv")`` — redacts named parameters (recorded as ``[REDACTED]``).
* ``@traced("a", "b")`` — explicit parameter names for ``*args`` cases with no bindable names.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from narrativetrace.template import resolve as _resolve_template

_F = TypeVar("_F", bound=Callable[..., object])

_NARRATED_ATTR = "__nt_narrated__"
_ON_ERRORS_ATTR = "__nt_on_errors__"
_NOT_TRACED_PARAMS_ATTR = "__nt_not_traced_params__"
_TRACED_NAMES_ATTR = "__nt_traced_names__"


def narrated(template: str) -> Callable[[_F], _F]:
    """Attaches a narration template resolved against the call's arguments."""

    def decorate(func: _F) -> _F:
        setattr(func, _NARRATED_ATTR, template)
        return func

    return decorate


def on_error(*args: object) -> Callable[[_F], _F]:
    """Attaches a stackable error-context template, matched against the raised type at exit."""
    exc_type, template = _parse_on_error_args(args)

    def decorate(func: _F) -> _F:
        errors = list(getattr(func, _ON_ERRORS_ATTR, ()))
        errors.append((exc_type, template))
        setattr(func, _ON_ERRORS_ATTR, errors)
        return func

    return decorate


def _parse_on_error_args(args: tuple[object, ...]) -> tuple[type[BaseException], str]:
    if len(args) == 1 and isinstance(args[0], str):
        return Exception, args[0]
    if (
        len(args) == 2
        and isinstance(args[0], type)
        and issubclass(args[0], BaseException)
        and isinstance(args[1], str)
    ):
        return args[0], args[1]
    raise TypeError("on_error expects (template) or (ExceptionType, template)")


def not_traced(*param_names: str) -> Callable[[_F], _F]:
    """Redacts the named parameters when the decorated method is traced."""

    def decorate(func: _F) -> _F:
        existing = set(getattr(func, _NOT_TRACED_PARAMS_ATTR, frozenset()))
        setattr(func, _NOT_TRACED_PARAMS_ATTR, frozenset(existing | set(param_names)))
        return func

    return decorate


def traced(*param_names: str) -> Callable[[_F], _F]:
    """Supplies explicit parameter names for calls whose signature cannot bind them."""

    def decorate(func: _F) -> _F:
        setattr(func, _TRACED_NAMES_ATTR, tuple(param_names))
        return func

    return decorate


@dataclass(frozen=True, slots=True)
class MethodMetadata:
    """Decoded decorator metadata for one traced callable."""

    narrated_template: str | None
    on_errors: tuple[tuple[type[BaseException], str], ...]
    not_traced_params: frozenset[str]
    traced_names: tuple[str, ...]


def read_method_metadata(func: Callable[..., object]) -> MethodMetadata:
    """Reads the decorator metadata attached to ``func`` (defaults when absent)."""
    return MethodMetadata(
        narrated_template=getattr(func, _NARRATED_ATTR, None),
        on_errors=tuple(getattr(func, _ON_ERRORS_ATTR, ())),
        not_traced_params=frozenset(getattr(func, _NOT_TRACED_PARAMS_ATTR, frozenset())),
        traced_names=tuple(getattr(func, _TRACED_NAMES_ATTR, ())),
    )


def resolve_error_context(
    on_errors: tuple[tuple[type[BaseException], str], ...],
    exception: BaseException,
    values: dict[str, object],
) -> str | None:
    """Resolves the most-specific matching ``@on_error`` template, or ``None`` when none match."""
    best: tuple[type[BaseException], str] | None = None
    for exc_type, template in on_errors:
        if isinstance(exception, exc_type) and (best is None or issubclass(exc_type, best[0])):
            best = (exc_type, template)
    if best is None:
        return None
    return _resolve_template(best[1], values)
