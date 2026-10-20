# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Request/user metadata wrappers and service identity stamped onto spans.

The typed value records ``HttpRoute``, ``ClientIp``, ``EnduserId``, ``SessionId``,
``TenantId`` and ``ServiceIdentity`` from the Java ``event`` package. The wrappers are thin
non-null value types that stay transparent in string contexts (JSON export, logging, OTel) and
serve as extension points for privacy behavior available in a paid tier.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar

_W = TypeVar("_W", bound="_StringWrapper")


class _StringWrapper:
    """Shared behaviour for non-null single-string value records."""

    value: str

    def __post_init__(self) -> None:
        if self.value is None:
            raise ValueError(f"{type(self).__name__} value must not be None")

    @classmethod
    def of(cls: type[_W], value: str) -> _W:
        """Creates a wrapper from a raw string."""
        return cls(value)  # type: ignore[call-arg]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class HttpRoute(_StringWrapper):
    """Request route or path template associated with a span."""

    value: str


@dataclass(frozen=True, slots=True)
class ClientIp(_StringWrapper):
    """Client network address copied onto a span at creation time."""

    value: str


@dataclass(frozen=True, slots=True)
class EnduserId(_StringWrapper):
    """End-user identity copied onto a span at creation time."""

    value: str


@dataclass(frozen=True, slots=True)
class SessionId(_StringWrapper):
    """Session correlation identifier copied onto a span at creation time."""

    value: str


@dataclass(frozen=True, slots=True)
class TenantId(_StringWrapper):
    """Tenant or account scope copied onto a span at creation time."""

    value: str


@dataclass(frozen=True, slots=True)
class ServiceIdentity:
    """Service metadata stamped onto every newly created span context.

    Only the name is needed to stop traces reading ``unknown_service:python``; version and
    environment stay ``None`` (not stamped) when nobody gave them.
    """

    service_name: str
    service_version: str | None = None
    environment: str | None = None

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> ServiceIdentity | None:
        """Reads the identity from the ``NARRATIVETRACE_SERVICE_NAME``,
        ``NARRATIVETRACE_SERVICE_VERSION`` and ``NARRATIVETRACE_ENVIRONMENT`` keys.

        Args:
            env: The mapping to read; ``os.environ`` when ``None``.

        Returns:
            The identity, or ``None`` when ``NARRATIVETRACE_SERVICE_NAME`` is unset or blank — a
            version or environment without a name is not an identity. A blank version or
            environment reads as unset.
        """
        source = os.environ if env is None else env
        name = _present(source, "NARRATIVETRACE_SERVICE_NAME")
        if name is None:
            return None
        return cls(
            name,
            _present(source, "NARRATIVETRACE_SERVICE_VERSION"),
            _present(source, "NARRATIVETRACE_ENVIRONMENT"),
        )


def _present(env: Mapping[str, str], key: str) -> str | None:
    """The value under ``key``, or ``None`` when it is absent or blank."""
    value = env.get(key)
    return value if value is not None and value.strip() else None
