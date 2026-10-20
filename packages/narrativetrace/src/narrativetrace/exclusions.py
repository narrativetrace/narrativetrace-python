# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Exclusion list 2 -- library and framework internals, named by module prefix, with a default.

Two exclusion lists exist. List 1 (:mod:`narrativetrace._generated`) is structural and fixed.
This is list 2: configurable, and it ships a default.

* **Key.** ``exclude`` -- ``exclude=`` on :func:`~narrativetrace.trace_object.trace_object`,
  ``NARRATIVETRACE_EXCLUDE`` in the environment, ``exclude`` in ``narrativetrace.toml`` or
  ``[tool.narrativetrace]`` (a ``;``-delimited string or a TOML array).
* **Replace, never merge.** The key's *presence* decides: absent means :data:`DEFAULT_EXCLUDE`;
  present -- even empty -- is the whole list. To extend the default, repeat its entries.
* **Matching** is delimiter-aware on ``.`` against the module that defines the target's type:
  ``acme.mocks`` matches ``acme.mocks`` and ``acme.mocks.deep``, never ``acme.mocksx``. A trailing
  ``.*`` / ``.**`` / ``.`` is accepted and means the same.
* **Report once per matched prefix** on stderr, never per target; the target then runs untraced.

**@llmNote** Python has no include list or import hook: ``trace_object`` wraps what the caller
hands it. So "included and excluded" means a target the caller wrapped whose type's module matches a
prefix -- the exclusion wins and the target comes back unwrapped. An explicit ``exclude=`` that is
malformed raises ``ValueError`` before any work; a malformed *configured* value must never throw
into the host's call, so it is reported once and the shipped default applies.
"""

from __future__ import annotations

import functools
import os
import re
import sys
import threading
from collections.abc import Sequence

from narrativetrace.config import ConfigResolver, DuplicateConfigurationError

EXCLUDE_REASONS: dict[str, str] = {
    "unittest": (
        "The standard library's test runner and, as `unittest.mock`, its mocking library: a "
        "generated `Mock` subclass records every call it receives"
    ),
    "mock": "The PyPI backport of `unittest.mock`, same generated mock classes",
    "pytest_mock": "pytest-mock's fixture helpers around `unittest.mock`",
    "pytest": "The test runner's own helpers",
    "_pytest": "The test runner's private implementation, which plugins and fixtures call into",
    "pluggy": "pytest's hook-calling machinery",
    "hypothesis": "The property-testing engine's own helpers and strategies",
    "coverage": "coverage.py's tracer and reporters",
    "narrativetrace": "This library's own types: tracing them would trace the tracer",
    "ddtrace": "Another APM agent's runtime: avoids recursive instrumentation when co-deployed",
    "opentelemetry": "The other APM runtime most likely to be co-deployed, same reason",
}
"""List 2's shipped default with the reason for each member, in order. Published verbatim by the
configuration guide, which a test holds to this mapping."""

DEFAULT_EXCLUDE: tuple[str, ...] = tuple(EXCLUDE_REASONS)
"""List 2's shipped default: the prefixes of :data:`EXCLUDE_REASONS`."""

_DOTTED_NAME = re.compile(r"[^\W\d]\w*(\.[^\W\d]\w*)*")
_WILDCARD_SUFFIXES = (".**", ".*", ".")


def _normalize(entry: str) -> str:
    normalized = entry.strip()
    for suffix in _WILDCARD_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    if not _DOTTED_NAME.fullmatch(normalized):
        raise ValueError(f"exclude entry {entry.strip()!r} is not a dotted module name")
    return normalized


class ExcludedModules:
    """An immutable, validated list of module prefixes plus the once-per-prefix report state."""

    def __init__(self, prefixes: Sequence[str]) -> None:
        seen: set[str] = set()
        for prefix in prefixes:
            if prefix in seen:
                raise ValueError(f"exclude lists {prefix} more than once")
            seen.add(prefix)
        self._prefixes = tuple(prefixes)
        self._reported: set[str] = set()
        self._lock = threading.Lock()

    @property
    def prefixes(self) -> tuple[str, ...]:
        """The normalized prefixes, in the order given."""
        return self._prefixes

    @classmethod
    def parse(cls, value: str) -> ExcludedModules:
        """Parses a ``;``-delimited value; ``ValueError`` on a malformed or repeated entry."""
        entries = [entry for entry in value.split(";") if entry.strip()]
        return cls([_normalize(entry) for entry in entries])

    @classmethod
    def resolve(cls, resolver: ConfigResolver) -> ExcludedModules:
        """The effective list: the resolved ``exclude`` value when the key is present, else the
        shipped default. Raises ``ValueError`` when the present value is malformed."""
        value = resolver.resolve("exclude", None)
        return cls(DEFAULT_EXCLUDE) if value is None else cls.parse(value)

    @classmethod
    def coerce(cls, option: ExcludedModules | str | Sequence[str] | None) -> ExcludedModules:
        """Turns ``trace_object``'s ``exclude=`` option into a list. ``None`` means "configured"
        (environment, file, default); equal explicit values share one report state."""
        if option is None:
            return _configured(os.getcwd(), os.environ.get("NARRATIVETRACE_EXCLUDE"))
        if isinstance(option, ExcludedModules):
            return option
        return _explicit(option if isinstance(option, str) else ";".join(option))

    def match(self, module: str | None) -> str | None:
        """The first prefix that excludes ``module`` (delimiter-aware), else ``None``."""
        if not module:
            return None
        for prefix in self._prefixes:
            if module == prefix or module.startswith(prefix + "."):
                return prefix
        return None

    def excludes(self, target: object) -> bool:
        """True when the module defining ``type(target)`` is excluded (reports each prefix once)."""
        cls = type(target)
        prefix = self.match(getattr(cls, "__module__", None))
        if prefix is None:
            return False
        self._report_once(prefix, f"{cls.__module__}.{cls.__name__}")
        return True

    def _report_once(self, prefix: str, class_path: str) -> None:
        with self._lock:
            if prefix in self._reported:
                return
            self._reported.add(prefix)
        _say(
            f"narrativetrace: cannot trace {class_path} (excluded module {prefix}); "
            "its calls run untraced"
        )


def _say(message: str) -> None:
    """Writes one diagnostic line to stderr; a broken stream is never the host's problem."""
    try:
        print(message, file=sys.stderr)
    except (OSError, ValueError):
        pass


@functools.lru_cache(maxsize=64)
def _explicit(value: str) -> ExcludedModules:
    return ExcludedModules.parse(value)


@functools.lru_cache(maxsize=64)
def _configured(cwd: str, environment_value: str | None) -> ExcludedModules:
    """The configured list for one working directory and environment value, resolved once.

    Keyed on both so a changed working directory or environment is seen; a config file edited
    mid-process is not (a restart picks it up). A failure to resolve falls back to the shipped
    default, said once -- tracing's own configuration must not throw into a business call.
    """
    del environment_value  # part of the cache key only; ConfigResolver reads the environment
    try:
        return ExcludedModules.resolve(ConfigResolver())
    except (ValueError, DuplicateConfigurationError) as error:
        _say(f"narrativetrace: ignoring the exclude setting ({error}); the shipped default applies")
        return ExcludedModules(DEFAULT_EXCLUDE)
