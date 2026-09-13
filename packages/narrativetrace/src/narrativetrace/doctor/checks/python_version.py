# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``toolchain.python-version`` — the running interpreter must satisfy the installed
``narrativetrace`` distribution's own ``Requires-Python`` (Installation Guide)."""

from __future__ import annotations

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding
from narrativetrace.doctor.version_lite import satisfies

ID = "toolchain.python-version"
_DEFAULT_RANGE = ">=3.12"


def _required_range(snapshot: DoctorSnapshot) -> str:
    core = snapshot.installed_packages.get("narrativetrace")
    return (core.requires_python if core is not None else None) or _DEFAULT_RANGE


def check_python_version(snapshot: DoctorSnapshot) -> Finding:
    required = _required_range(snapshot)
    if satisfies(snapshot.python_version, required):
        return passed(
            ID,
            f"Python {snapshot.python_version} satisfies the required {required}",
            DOC["installation_prerequisites"],
        )
    return failed(
        ID,
        f"Python {snapshot.python_version} does not satisfy the required {required}",
        f"Upgrade Python to a version satisfying {required} (pyenv, asdf, or your CI image), "
        "then re-run `uv sync`.",
        DOC["installation_prerequisites"],
    )
