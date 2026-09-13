# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The doctor's world-view, decoupled from the real filesystem (mirrors the TypeScript runtime's
``doctor/types.ts``): every check is a pure function over a :class:`DoctorSnapshot`, which is why
every check has both a passing and a failing unit test with no disk I/O at all.
:func:`~narrativetrace.doctor.environment.build_snapshot` is the one impure module — it walks the
real project and installed-distribution metadata once per run and builds this shape.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

Env = Mapping[str, str]
"""The process environment, as ``os.environ`` hands it over."""


@dataclass(frozen=True, slots=True)
class PackageInfo:
    """The subset of an installed distribution's metadata a check ever needs."""

    name: str
    version: str
    requires_python: str | None = None
    requires: tuple[str, ...] = ()
    """Raw ``Requires-Dist`` entries (PEP 508 strings), e.g. ``"pytest>=8"``."""


@dataclass(frozen=True, slots=True)
class DoctorSnapshot:
    """Everything a check can read. Immutable — a check receives one snapshot and returns one
    :class:`Finding`; nothing here is ever mutated by a check (the read-only invariant)."""

    cwd: str
    """Absolute path to the project being checked (informational — checks never touch disk)."""
    python_version: str
    """``sys.version_info`` rendered as ``"3.12.4"``."""
    env: Env
    root_pyproject: Mapping[str, object] | None
    """The parsed root ``pyproject.toml``, or ``None`` when absent/unreadable."""
    narrativetrace_config: Mapping[str, object]
    """The resolved ``[tool.narrativetrace]``-shaped table (env excluded) — see
    :class:`~narrativetrace.config.ConfigResolver`'s file precedence. Empty when no config file
    was discovered."""
    source_files: Mapping[str, str] = field(default_factory=dict)
    """Relative path -> content, for source/config/test files under the project (bounded walk)."""
    output_files: Mapping[str, str] = field(default_factory=dict)
    """Relative path -> content, for everything under the configured output directory."""
    approved_dir_files: Mapping[str, str] = field(default_factory=dict)
    """Relative path -> content, for everything under the configured approved-trace directory."""
    installed_packages: Mapping[str, PackageInfo] = field(default_factory=dict)
    """Distribution name -> its resolved metadata, for distributions the checks care about."""
    pytest11_entry_points: Mapping[str, str] = field(default_factory=dict)
    """Registered ``pytest11`` entry point name -> the module it loads, from whatever is
    installed in this environment (``importlib.metadata.entry_points(group="pytest11")``)."""


FindingStatus = Literal["pass", "fail"]


@dataclass(frozen=True, slots=True)
class Finding:
    """One check's result."""

    id: str
    """Stable, dotted id (``"toolchain.python-version"``) — never renamed once shipped; agents
    and CI grep it."""
    status: FindingStatus
    message: str
    """One line: what the check found, true on pass or fail."""
    fix: str
    """What to do about it. Empty string on a pass — there is nothing to fix."""
    doc_url: str
    """Public doc URL the finding points at (a GitHub blob link into this repo's
    ``documentation/``)."""


DoctorCheck = Callable[[DoctorSnapshot], Finding]


@dataclass(frozen=True, slots=True)
class DoctorReport:
    findings: tuple[Finding, ...]
    exit_code: Literal[0, 1]
    """0 — every check passed. 1 — at least one finding failed."""
