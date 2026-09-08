# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Semantic signature recorded for a traced invocation.

``MethodSignature`` and ``ParameterCapture``. This is the handoff point between live
Python objects and the immutable trace model: values are rendered once at capture time so later
renderers never touch reflection or live objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from narrativetrace.values import RenderedValue


@dataclass(frozen=True, slots=True)
class ParameterCapture:
    """Eager capture of one parameter name and its rendered value.

    ``rendered_value`` is the pre-rendered textual value (strings include quotes, scalars use
    plain text; non-``DETAIL`` levels may suppress it as an empty string). ``structured_value``
    is the optional type-preserving companion for typed OTel export, ``None`` when not captured
    or when the parameter is redacted. ``type_name`` is the declared annotation (canonical schema
    1.2, ``nt.parameters[].type``), ``None`` for an unannotated parameter — it is what makes two
    same-named methods distinguishable to a cross-platform consumer.
    """

    name: str
    rendered_value: str
    redacted: bool = False
    structured_value: RenderedValue | None = None
    type_name: str | None = None


@dataclass(frozen=True, slots=True)
class MethodSignature:
    """Stable description of a call: names, eager parameter captures, and resolved narration.

    ``narration`` holds a resolved ``@narrated`` template (or ``None``); ``error_context`` holds
    a resolved ``@on_error`` template attached to a failing exit (or ``None``).

    The remaining fields complete the call's *identity* for the canonical schema, and are all
    additive and nullable:

    * ``narration_template`` — the **raw** ``@narrated`` text with its ``{placeholders}`` intact
      (schema 1.1, ``nt.narrationTemplate``). ``narration`` is the same template already filled in,
      so a translated view needs this one: it re-renders the per-locale variant and fills the
      placeholders from untouched values.
    * ``package_name`` — the module owning the traced class (schema 1.2, ``nt.package``).
      ``class_name`` deliberately stays a simple name for readability; this completes the identity.
    * ``return_type`` — the declared return annotation (schema 1.2, ``nt.returnType``).
    """

    class_name: str
    method_name: str
    parameters: list[ParameterCapture] = field(default_factory=list)
    narration: str | None = None
    error_context: str | None = None
    narration_template: str | None = None
    package_name: str | None = None
    return_type: str | None = None
