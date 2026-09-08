# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Structured value representation preserving original Python types.

``RenderedValue`` (``ai.narrativetrace.core.event``). Alongside the flat string
rendering, this union preserves type information for downstream consumers — primarily the OTel
exporter (PY10) that emits typed span attributes. The renderer that *produces* these lands in
PY2; this module is data only.

Java→Python type mapping (documented divergence in naming, identical intent):

* ``LongVal`` → :class:`IntVal` (Python ints are unbounded)
* ``DoubleVal`` → :class:`FloatVal`
* ``BooleanVal`` → :class:`BoolVal`
"""

from __future__ import annotations

from dataclasses import dataclass


class RenderedValue:
    """Base of the sealed structured-value union. Not instantiated directly."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class StringVal(RenderedValue):
    """A string value (also used for enums, chars, and custom ``__str__`` fallbacks)."""

    value: str


@dataclass(frozen=True, slots=True)
class IntVal(RenderedValue):
    """An integral numeric value (Java int/long/short/byte)."""

    value: int


@dataclass(frozen=True, slots=True)
class FloatVal(RenderedValue):
    """A floating-point numeric value (Java float/double/BigDecimal)."""

    value: float


@dataclass(frozen=True, slots=True)
class BoolVal(RenderedValue):
    """A boolean value."""

    value: bool


@dataclass(frozen=True, slots=True)
class InstantVal(RenderedValue):
    """A timestamp as epoch milliseconds, distinguished from :class:`IntVal` for range queries."""

    epoch_millis: int


@dataclass(frozen=True, slots=True)
class ObjectVal(RenderedValue):
    """A structured object with named fields, preserving field types."""

    type_name: str
    fields: dict[str, RenderedValue]


@dataclass(frozen=True, slots=True)
class ListVal(RenderedValue):
    """An ordered collection of values (from lists, sets, tuples, arrays)."""

    elements: list[RenderedValue]


@dataclass(frozen=True, slots=True)
class NullVal(RenderedValue):
    """A null / ``None`` value."""
