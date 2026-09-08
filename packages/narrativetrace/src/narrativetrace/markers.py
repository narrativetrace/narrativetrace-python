# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Field-level ``not_traced`` marker mechanism consumed by value introspection.

The field/record-component ``@NotTraced`` marker from Java. Python has two supported
surfaces (plan decision point 2):

* a class attribute ``__nt_not_traced__`` listing field names, and
* a dataclass field ``metadata={"narrativetrace": "not_traced"}`` (use :func:`not_traced_field`).

The parameter-level ``@not_traced`` decorator lands in PY3; this module is only the field surface
the renderer honours.
"""

from __future__ import annotations

import dataclasses
from typing import Any

_METADATA_KEY = "narrativetrace"
_NOT_TRACED = "not_traced"

NOT_TRACED_METADATA = {_METADATA_KEY: _NOT_TRACED}
"""Metadata mapping to attach to a ``dataclasses.field`` to mark it not-traced."""


def not_traced_field(**kwargs: Any) -> Any:
    """A ``dataclasses.field`` marked not-traced; extra keyword args pass through to ``field``."""
    metadata = {**kwargs.pop("metadata", {}), **NOT_TRACED_METADATA}
    return dataclasses.field(metadata=metadata, **kwargs)


def is_field_not_traced(owner: type, field_name: str) -> bool:
    """Whether ``field_name`` on ``owner`` is marked not-traced by either supported surface."""
    explicit = getattr(owner, "__nt_not_traced__", None)
    if explicit is not None and field_name in explicit:
        return True
    if dataclasses.is_dataclass(owner):
        for field in dataclasses.fields(owner):
            if field.name == field_name:
                return field.metadata.get(_METADATA_KEY) == _NOT_TRACED
    return False


_NARRATIVE_SUMMARY_ATTR = "__nt_narrative_summary__"


def narrative_summary(method: Any) -> Any:
    """Marks a zero-argument method as the narrative summary used by the value renderer."""
    method.__nt_narrative_summary__ = True
    return method
