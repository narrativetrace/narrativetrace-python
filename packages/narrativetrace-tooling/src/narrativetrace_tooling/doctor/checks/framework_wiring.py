# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.<framework>-*`` — one framework-table row, observed from manifests and source: the
framework is present but its integration distribution is not declared, or the distribution is
declared but its wiring is never applied. A row whose framework has no integration shipped is
REPORTED (a pass, nothing to fix) so an agent leaves it alone instead of guessing. Mirrors Java's
``FrameworkWiringCheck``; one generic check built per row, never a class per framework.

INTENT: the ``add-narrative-tracing`` skill lists no framework; its framework step runs the doctor
and applies every ``config.<framework>-*`` fix in order. So every failing fix here is complete on
its own: the ``uv add`` line pinned to the project's own NarrativeTrace version, then the row's
wiring lines verbatim — a fixture's text, from
:mod:`~narrativetrace_tooling.frameworks.wiring_snippets`.

**@llmNote** Text and manifest only, never an import of the project, and both over the SAME walked
tree: a parent's ``pyproject.toml`` found by walking up is not read, because the wiring it would
ask for lives outside the walk. Presence and reference are what the manifests declare
(:mod:`~narrativetrace_tooling.frameworks.manifests`), wiring is what the project's ``.py`` files
use (:mod:`~narrativetrace_tooling.frameworks.evidence`). A project that neither uses the
framework nor declares the integration passes — a check fails a project for
what it got wrong, never for what it does not use.
"""

from __future__ import annotations

from typing import Final

from narrativetrace_tooling.doctor.doc_urls import DOC
from narrativetrace_tooling.doctor.finding import failed, passed
from narrativetrace_tooling.doctor.types import DoctorCheck, DoctorSnapshot, Finding
from narrativetrace_tooling.frameworks.evidence import is_test_source
from narrativetrace_tooling.frameworks.manifests import declared_distributions
from narrativetrace_tooling.frameworks.table import (
    FrameworkRow,
    IntegrationModule,
    NoIntegration,
    Snippet,
    WiringCheck,
    detected,
)
from narrativetrace_tooling.frameworks.wiring_snippets import text

VERSION_PLACEHOLDER: Final = "<your narrativetrace version>"
"""What the ``uv add`` line pins to when the project resolves no NarrativeTrace release yet."""


def framework_wiring_check(framework: FrameworkRow) -> DoctorCheck:
    """The doctor check for one table row.

    :raises ValueError: for a row the table binds to no ``config.<framework>-*`` check.
    """
    if not isinstance(framework.check, WiringCheck):
        raise ValueError(f"row {framework.id} has no config.<framework>-* check")
    check_id = framework.check.id

    def check(snapshot: DoctorSnapshot) -> Finding:
        return _run(framework, check_id, snapshot)

    check.__name__ = f"check_{framework.id.replace('-', '_')}_wiring"
    return check


def _run(framework: FrameworkRow, check_id: str, snapshot: DoctorSnapshot) -> Finding:
    declared = declared_distributions(snapshot.source_files)
    module, wiring = framework.module, framework.wiring
    referenced = module is not None and module.referenced_in(declared)
    if not referenced and not detected(framework, declared):
        return passed(check_id, f"{framework.name} not detected — nothing to wire", _DOC)
    if isinstance(wiring, NoIntegration):
        return passed(check_id, _no_integration_message(framework), _DOC)
    assert module is not None  # a row that ships wiring adds a module (FrameworkRow's invariant)
    if not referenced:
        return _not_referenced(framework, module, wiring, check_id, snapshot)
    if wiring.applied_in(_python_sources(snapshot, wiring.in_tests)):
        return passed(check_id, f"{module.distribution} is wired: {wiring.description}", _DOC)
    return failed(
        check_id,
        f"{module.distribution} is referenced but its wiring ({wiring.description}) is never "
        f"applied — {wiring.unwired}",
        "Apply the wiring: " + _wiring_fix(framework, wiring),
        _DOC,
    )


_DOC: Final = DOC["framework_table"]


def _no_integration_message(framework: FrameworkRow) -> str:
    return (
        f"{framework.name} detected ({framework.marker.description}) — no integration shipped; "
        "leave it alone and trace its services with trace_object"
    )


def _not_referenced(
    framework: FrameworkRow,
    module: IntegrationModule,
    wiring: Snippet,
    check_id: str,
    snapshot: DoctorSnapshot,
) -> Finding:
    version = snapshot.narrativetrace_version or VERSION_PLACEHOLDER
    return failed(
        check_id,
        f"{framework.name} detected ({framework.marker.description}) but "
        f"{module.distribution} is not referenced — {wiring.unwired}",
        f"Add {module.distribution}: {module.add_instruction(version)}. Then "
        + _wiring_fix(framework, wiring),
        _DOC,
    )


def _wiring_fix(framework: FrameworkRow, wiring: Snippet) -> str:
    return (
        f"add {wiring.description}, adapted to this project's own app and services "
        f"(from {wiring.fixture}):\n{text(framework.id)}"
    )


def _python_sources(snapshot: DoctorSnapshot, in_tests: bool) -> list[str]:
    """The project's ``.py`` files the row's evidence may be found in — test modules only when the
    row's wiring lives in tests."""
    return [
        content
        for path, content in snapshot.source_files.items()
        if path.endswith(".py") and (in_tests or not is_test_source(path))
    ]
