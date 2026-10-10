# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The framework table — Phase 6's D1: ONE committed registry of which frameworks NarrativeTrace
integrates with, how a project proves it uses one, which distribution it adds, how that is wired,
and which doctor check watches the wiring. Mirrors Java's ``FrameworkTable``; the row SHAPE, the
check naming and the hand-off step are the cross-port contract, the rows are this runtime's own.

INTENT: the table ships inside the library the doctor runs from, so a project is measured against
the rows of the NarrativeTrace version it actually installed — never against the repository or the
live docs, which describe the newest release. The ``add-narrative-tracing`` skill lists no
framework at all; it runs the doctor and applies every ``config.<framework>-*`` fix the doctor
prints. ``llms-full.md``'s framework table and ``llms.txt``'s covered-frameworks line render from
these rows (:mod:`~narrativetrace_tooling.frameworks.docs`).

**@llmNote** Adding a framework is adding a row here and, when its wiring is source-level, a fixture
the suite runs plus its section in ``wiring-snippets.md``: the doctor check, the docs and the skill
follow without new code. Row ids and check ids are a cross-port contract — append, never rename.
A framework with no integration shipped is a row too: its check REPORTS it (always a pass, nothing
to fix) so an agent leaves it alone instead of guessing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from narrativetrace_tooling.frameworks.evidence import Evidence, RequestsFixture, UsesName
from narrativetrace_tooling.frameworks.manifests import normalize

NO_TIER_B_CASE: Final = "none"
"""The :attr:`FrameworkRow.tier_b_case` of a row no Tier B case exercises yet."""

_KEBAB: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_WIRING_CHECK_ID: Final = re.compile(r"config\.[a-z0-9]+(?:-[a-z0-9]+)+")


@dataclass(frozen=True, slots=True)
class Marker:
    """What in a project's manifests proves a framework is present — the first column.

    ``distributions`` are matched, PEP 503-normalized, against what the project's manifests declare
    (:func:`~narrativetrace_tooling.frameworks.manifests.declared_distributions`); empty for a row
    whose presence is never read from a manifest. ``defer_to`` names rows that take precedence: a
    row stands down while any of them is detected too."""

    description: str
    distributions: tuple[str, ...]
    defer_to: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("a marker's description must not be blank")


@dataclass(frozen=True, slots=True)
class IntegrationModule:
    """The NarrativeTrace distribution a row adds, and whether it is a development dependency."""

    distribution: str
    dev: bool = False

    def referenced_in(self, declared: frozenset[str]) -> bool:
        """Whether the project's manifests already declare the distribution."""
        return normalize(self.distribution) in declared

    def add_instruction(self, narrativetrace_version: str) -> str:
        """The ``uv add`` line, pinned to the project's own NarrativeTrace version so the
        lockstep check (``toolchain.package-versions``) keeps holding."""
        flag = "--dev " if self.dev else ""
        return f'uv add {flag}"{self.distribution}=={narrativetrace_version}"'


@dataclass(frozen=True, slots=True)
class Snippet:
    """Wiring a project writes into its own source. The lines are NEVER typed here: ``fixture``
    (repository-relative) and ``region`` name a fixture the suite runs, and the text a reader sees
    is that fixture's, carried by :mod:`~narrativetrace_tooling.frameworks.wiring_snippets`.
    ``evidence`` is what in the project's Python source proves the wiring applied — any one
    suffices; ``unwired`` is what a project loses while the wiring is missing, in the words the
    doctor's message ends with. ``in_tests`` says whether a test module counts as evidence: for
    every row but pytest's it does not, since middleware a test builds around its own app leaves
    the real one unwired."""

    description: str
    fixture: str
    region: str
    evidence: tuple[Evidence, ...]
    unwired: str
    in_tests: bool = False

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError("source wiring needs evidence the doctor can look for")

    def applied_in(self, sources: Iterable[str]) -> bool:
        """Whether any of the project's Python sources shows the wiring applied."""
        return any(e.found_in(source) for source in sources for e in self.evidence)


@dataclass(frozen=True, slots=True)
class NoIntegration:
    """No NarrativeTrace integration ships for this framework: the doctor reports it, an agent
    leaves it alone, and the framework's code is traced the ordinary way (``trace_object``)."""

    description: str


Wiring = Snippet | NoIntegration


@dataclass(frozen=True, slots=True)
class WiringCheck:
    """A ``config.<framework>-<thing>`` check the doctor runs for this row."""

    id: str

    def __post_init__(self) -> None:
        if _WIRING_CHECK_ID.fullmatch(self.id) is None:
            raise ValueError(f"a framework check id is config.<framework>-<thing>, got {self.id!r}")


@dataclass(frozen=True, slots=True)
class NoCheck:
    """Nothing in a manifest or a source file can show this row's wiring — said, never a vague
    pass."""

    reason: str


CheckBinding = WiringCheck | NoCheck


@dataclass(frozen=True, slots=True)
class FrameworkRow:
    """One row: marker → module → wiring → doctor check → Tier B case."""

    id: str
    name: str
    marker: Marker
    module: IntegrationModule | None
    wiring: Wiring
    check: CheckBinding
    tier_b_case: str

    def __post_init__(self) -> None:
        if _KEBAB.fullmatch(self.id) is None:
            raise ValueError(f"a row id is kebab-case, got {self.id!r}")
        if not self.name.strip():
            raise ValueError(f"row {self.id} names no framework")
        if not self.tier_b_case.strip():
            raise ValueError(f"row {self.id} names a Tier B case or none")
        if isinstance(self.wiring, NoIntegration) and self.module is not None:
            raise ValueError(f"row {self.id}: no integration shipped adds no module")
        if self.module is None and not isinstance(self.wiring, NoIntegration):
            raise ValueError(f"row {self.id} adds no module but ships wiring")


def _unsupported(row_id: str, name: str, distribution: str) -> FrameworkRow:
    return FrameworkRow(
        row_id,
        name,
        Marker(f"a {distribution} dependency", (distribution,)),
        None,
        NoIntegration("no integration shipped — trace its services with trace_object"),
        WiringCheck(f"config.{row_id}-integration"),
        NO_TIER_B_CASE,
    )


ROWS: Final[tuple[FrameworkRow, ...]] = (
    FrameworkRow(
        "pytest",
        "pytest",
        Marker("a pytest dependency", ("pytest",)),
        IntegrationModule("narrativetrace-pytest", dev=True),
        Snippet(
            "the narrative_trace fixture, requested by a test",
            "packages/narrativetrace-pytest/tests/fixture_wiring.py",
            "wiring",
            (RequestsFixture("narrative_trace"),),
            "no test is traced",
            in_tests=True,
        ),
        WiringCheck("config.pytest-fixture"),
        NO_TIER_B_CASE,
    ),
    FrameworkRow(
        "asgi",
        "FastAPI / Starlette (ASGI)",
        Marker("a fastapi or starlette dependency", ("fastapi", "starlette")),
        IntegrationModule("narrativetrace-asgi"),
        Snippet(
            "NarrativeTraceMiddleware on the ASGI app, with an exporter",
            "packages/narrativetrace-asgi/tests/asgi_wiring.py",
            "wiring",
            (UsesName("NarrativeTraceMiddleware"),),
            "no request is traced",
        ),
        WiringCheck("config.asgi-middleware"),
        "init-prompt-fastapi-project",
    ),
    FrameworkRow(
        "opentelemetry",
        "OpenTelemetry",
        Marker(
            "an opentelemetry-api or -sdk dependency", ("opentelemetry-api", "opentelemetry-sdk")
        ),
        IntegrationModule("narrativetrace-otel"),
        Snippet(
            "OtelTraceEventListener on the context's event pipeline",
            "packages/narrativetrace-otel/tests/otel_wiring.py",
            "wiring",
            (UsesName("OtelTraceEventListener"), UsesName("TraceSpanExporter")),
            "no span reaches OpenTelemetry",
        ),
        WiringCheck("config.otel-listener"),
        NO_TIER_B_CASE,
    ),
    FrameworkRow(
        "structlog",
        "structlog",
        Marker("a structlog dependency", ("structlog",)),
        IntegrationModule("narrativetrace-structlog"),
        Snippet(
            "narrative_context_processor in structlog.configure's processors",
            "packages/narrativetrace-structlog/tests/structlog_wiring.py",
            "wiring",
            (UsesName("narrative_context_processor"),),
            "no structlog event carries the trace's keys",
        ),
        WiringCheck("config.structlog-processor"),
        NO_TIER_B_CASE,
    ),
    FrameworkRow(
        "default-logger",
        "stdlib logging",
        Marker("the default logger: the program configures no logging handler", ()),
        IntegrationModule("narrativetrace"),
        Snippet(
            "a stdlib handler carrying NarrativeContextFilter, and export_to_logger(trace)",
            "packages/narrativetrace/tests/logging_wiring.py",
            "wiring",
            (UsesName("NarrativeContextFilter"), UsesName("export_to_logger")),
            "no trace reaches the logger",
        ),
        NoCheck(
            "runtime-only — whether a handler exists is decided when the program configures "
            "logging, not visible in a manifest"
        ),
        NO_TIER_B_CASE,
    ),
    _unsupported("flask", "Flask", "flask"),
    _unsupported("django", "Django", "django"),
)


def row(row_id: str) -> FrameworkRow:
    """The row with this id.

    :raises KeyError: when the table has none — naming the id, so a typo is never a silent miss.
    """
    for candidate in ROWS:
        if candidate.id == row_id:
            return candidate
    raise KeyError(f"no framework row {row_id}")


def rows_with_wiring_checks() -> tuple[FrameworkRow, ...]:
    """The rows that earn a doctor check of their own, in table order."""
    return tuple(r for r in ROWS if isinstance(r.check, WiringCheck))


def wiring_check_ids() -> tuple[str, ...]:
    """Every ``config.<framework>-*`` id the doctor runs, in table order."""
    return tuple(r.check.id for r in rows_with_wiring_checks() if isinstance(r.check, WiringCheck))


def detected(framework: FrameworkRow, declared: frozenset[str]) -> bool:
    """Whether the project's declared distributions show ``framework``: one of its marker
    distributions is declared, and no row it defers to is detected as well.

    :raises KeyError: when the row defers to an id the table has no row for — a typo there would
        otherwise make the row silently never stand down.
    """
    marked = any(normalize(d) in declared for d in framework.marker.distributions)
    return marked and not any(detected(row(other), declared) for other in framework.marker.defer_to)
