# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``toolchain.package-versions`` — the eight NarrativeTrace distributions are versioned in
lockstep; whichever subset is installed must all report the SAME version, or a consumer that also
depends on one directly can end up pinning two of them apart (one from this project's own
constraint, one pulled in transitively) with no error until behavior quietly disagrees."""

from __future__ import annotations

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "toolchain.package-versions"

NARRATIVETRACE_DISTRIBUTIONS = (
    "narrativetrace",
    "narrativetrace-asgi",
    "narrativetrace-clarity",
    "narrativetrace-diagrams",
    "narrativetrace-glossary",
    "narrativetrace-otel",
    "narrativetrace-pytest",
    "narrativetrace-structlog",
)


def check_package_versions(snapshot: DoctorSnapshot) -> Finding:
    installed = {
        name: pkg.version
        for name in NARRATIVETRACE_DISTRIBUTIONS
        if (pkg := snapshot.installed_packages.get(name)) is not None
    }
    if len(installed) < 2:
        message = f"{len(installed)} NarrativeTrace package(s) installed — nothing to compare"
        return passed(ID, message, DOC["installation_prerequisites"])
    versions = set(installed.values())
    if len(versions) == 1:
        version = next(iter(versions))
        message = f"all {len(installed)} installed NarrativeTrace package(s) agree at {version}"
        return passed(ID, message, DOC["installation_prerequisites"])
    by_version = ", ".join(f"{name}=={version}" for name, version in sorted(installed.items()))
    message = f"installed NarrativeTrace packages disagree on version: {by_version}"
    fix = (
        "Pin every narrativetrace-* dependency to the same version and re-run `uv sync` — a "
        "mismatched sibling is the one failure mode that breaks the packages' own contract with "
        "each other."
    )
    return failed(ID, message, fix, DOC["installation_prerequisites"])
