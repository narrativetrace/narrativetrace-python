# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""W3C-compliant trace and span identifier value types.

``TraceId``, ``SpanId``, ``HexValidator`` and ``SpanIdGenerator`` from the Java
``ai.narrativetrace.core.event`` package. Validation happens at construction time, so any
instance is guaranteed valid, and ``str()`` returns the raw hex — the types stay transparent
in logging, JSON export, and OTel attribute contexts.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from narrativetrace.namer import trace_name

_HEX_DIGITS = "0123456789abcdef"


def _is_lowercase_hex(value: str) -> bool:
    return all(c in _HEX_DIGITS for c in value)


def _require_valid_hex(value: str, length: int, field: str) -> None:
    if len(value) != length or not _is_lowercase_hex(value):
        raise ValueError(f"{field} must be {length} lowercase hex characters")


def _random_hex(byte_count: int) -> str:
    return secrets.token_bytes(byte_count).hex()


@dataclass(frozen=True, slots=True)
class TraceId:
    """A W3C trace-id: exactly 32 lowercase hexadecimal characters."""

    value: str

    _LENGTH = 32

    def __post_init__(self) -> None:
        _require_valid_hex(self.value, self._LENGTH, "traceId")

    @classmethod
    def generate(cls) -> TraceId:
        """Generates a random trace id from 16 cryptographically random bytes."""
        return cls(_random_hex(16))

    def human_name(self) -> str:
        """A deterministic three-word "adjective noun verb" phrase derived from this id."""
        return trace_name(self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SpanId:
    """A W3C span id: exactly 16 lowercase hexadecimal characters."""

    value: str

    _LENGTH = 16

    def __post_init__(self) -> None:
        _require_valid_hex(self.value, self._LENGTH, "spanId")

    @classmethod
    def generate(cls) -> SpanId:
        """Generates a random span id from 8 cryptographically random bytes."""
        return cls(_random_hex(8))

    def __str__(self) -> str:
        return self.value
