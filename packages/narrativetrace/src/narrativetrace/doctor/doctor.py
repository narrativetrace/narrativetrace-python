# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Every check ``narrativetrace doctor`` runs, in stable, documented order. Adding a check means
appending here — the id is what stays stable across releases, not the position."""

from __future__ import annotations

from narrativetrace.doctor.checks.approval_traces import check_approval_traces
from narrativetrace.doctor.checks.llms_before_you_start import check_llms_before_you_start
from narrativetrace.doctor.checks.not_traced_unused import check_not_traced_unused
from narrativetrace.doctor.checks.output_env import check_output_env
from narrativetrace.doctor.checks.package_versions import check_package_versions
from narrativetrace.doctor.checks.parameter_names import check_parameter_names
from narrativetrace.doctor.checks.pytest_plugin_registered import check_pytest_plugin_registered
from narrativetrace.doctor.checks.pytest_version import check_pytest_version
from narrativetrace.doctor.checks.python_version import check_python_version
from narrativetrace.doctor.checks.redaction_proof import check_redaction_proof
from narrativetrace.doctor.checks.unknown_config_keys import check_unknown_config_keys
from narrativetrace.doctor.types import DoctorCheck, DoctorReport, DoctorSnapshot

DOCTOR_CHECKS: tuple[DoctorCheck, ...] = (
    check_python_version,
    check_pytest_version,
    check_package_versions,
    check_output_env,
    check_pytest_plugin_registered,
    check_unknown_config_keys,
    check_not_traced_unused,
    check_parameter_names,
    check_redaction_proof,
    check_approval_traces,
    check_llms_before_you_start,
)


def run_doctor(snapshot: DoctorSnapshot) -> DoctorReport:
    """Runs every check over ``snapshot`` and derives the process exit code. Read-only: mutates
    nothing."""
    findings = tuple(check(snapshot) for check in DOCTOR_CHECKS)
    any_failed = any(finding.status == "fail" for finding in findings)
    return DoctorReport(findings=findings, exit_code=1 if any_failed else 0)
