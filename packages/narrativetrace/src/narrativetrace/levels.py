# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tracing verbosity level and runtime configuration.

``TracingLevel`` and ``NarrativeTraceConfig``. ``from_name`` is the single
lenient parse point: garbage degrades to a fallback rather than crashing capture — an unreadable
config value must never take capture down with it.

Where the value comes from is :mod:`narrativetrace.config`'s concern:
:meth:`NarrativeTraceConfig.resolve` reads the ``level`` key through a
:class:`~narrativetrace.config.ConfigResolver`, so the environment beats a config file which beats
the default, mirroring Java's system-property-beats-properties-file chain.
"""

from __future__ import annotations

from enum import Enum

from narrativetrace.config import ConfigResolver


class TracingLevel(Enum):
    """How much of the captured event stream survives into the final trace tree.

    Levels are ordered by increasing verbosity; :meth:`is_enabled` compares by ``rank`` so a
    more verbose level implies all less verbose behaviours.
    """

    OFF = 0
    ERRORS = 1
    SUMMARY = 2
    NARRATIVE = 3
    DETAIL = 4

    @property
    def rank(self) -> int:
        """Ordinal used for verbosity comparison (OFF=0 … DETAIL=4)."""
        return self.value

    def is_enabled(self, required: TracingLevel) -> bool:
        """Returns whether this level is at least as verbose as ``required``."""
        return self.rank >= required.rank

    @classmethod
    def from_name(cls, name: str | None, fallback: TracingLevel) -> TracingLevel:
        """Parses a level name, tolerating case/whitespace, degrading garbage to ``fallback``."""
        if name is None or not name.strip():
            return fallback
        try:
            return cls[name.strip().upper()]
        except KeyError:
            return fallback


class NarrativeTraceConfig:
    """Mutable tracing configuration. ``level`` may be changed at runtime."""

    def __init__(self, level: TracingLevel = TracingLevel.DETAIL) -> None:
        self.level = level

    @classmethod
    def resolve(
        cls,
        default: TracingLevel = TracingLevel.DETAIL,
        resolver: ConfigResolver | None = None,
    ) -> NarrativeTraceConfig:
        """Builds a config from the resolved ``level`` key, degrading garbage to ``default``.

        Pass ``resolver`` to control the discovery root (tests, or an app that configures from a
        directory other than the working one); the default resolver walks up from the cwd.
        """
        active = resolver if resolver is not None else ConfigResolver()
        return cls(TracingLevel.from_name(active.resolve("level"), default))
