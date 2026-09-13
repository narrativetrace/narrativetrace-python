# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``toolchain.pytest-version`` — the installed ``pytest`` must satisfy
``narrativetrace-pytest``'s own declared dependency range on it."""

from __future__ import annotations

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding, PackageInfo
from narrativetrace.doctor.version_lite import dependency_specifier, satisfies

ID = "toolchain.pytest-version"


def _no_pytest_installed(specifier: str) -> Finding:
    message = f"narrativetrace-pytest requires pytest{specifier}, but no pytest install was found"
    fix = f"Install a pytest version satisfying {specifier} (uv add --dev 'pytest{specifier}')."
    return failed(ID, message, fix, DOC["pytest_configuration"])


def _mismatched_pytest(specifier: str, installed: str) -> Finding:
    message = (
        f"pytest {installed} does not satisfy narrativetrace-pytest's declared range {specifier}"
    )
    fix = f"Install a pytest version satisfying {specifier}, then `uv sync` for a clean install."
    return failed(ID, message, fix, DOC["pytest_configuration"])


def _evaluate(specifier: str, pytest_pkg: PackageInfo | None) -> Finding:
    if pytest_pkg is None:
        return _no_pytest_installed(specifier)
    if satisfies(pytest_pkg.version, specifier):
        message = f"pytest {pytest_pkg.version} satisfies the declared range {specifier}"
        return passed(ID, message, DOC["pytest_configuration"])
    return _mismatched_pytest(specifier, pytest_pkg.version)


def check_pytest_version(snapshot: DoctorSnapshot) -> Finding:
    nt_pytest = snapshot.installed_packages.get("narrativetrace-pytest")
    specifier = dependency_specifier(nt_pytest.requires, "pytest") if nt_pytest else None
    if nt_pytest is None or specifier is None:
        return passed(
            ID,
            "narrativetrace-pytest is not installed — nothing to check",
            DOC["pytest_configuration"],
        )
    return _evaluate(specifier, snapshot.installed_packages.get("pytest"))
