# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The doctor's finding count the skills verify against is the registry's count (cross-port item
7): a check added to the doctor — a framework-table row, most often — moves every published count
in one change, and this test is what notices the one that did not."""

from __future__ import annotations

import re
from pathlib import Path

from narrativetrace_skills.catalogue.doctor_commands import DOCTOR_REPORT_WELL_FORMED

from narrativetrace_tooling.doctor.doctor import DOCTOR_CHECKS


def test_the_well_formed_report_verify_counts_every_registered_check() -> None:
    counts = re.findall(r"len\(findings\) != (\d+)", DOCTOR_REPORT_WELL_FORMED)
    assert counts == [str(len(DOCTOR_CHECKS))]


def test_the_doctor_happy_path_grader_counts_every_registered_check() -> None:
    grader = (
        Path(__file__).resolve().parents[1]
        / "evals/narrativetrace-doctor/happy-path/graders/verify.sh"
    ).read_text(encoding="utf-8")
    assert re.findall(r"len\(findings\) != (\d+)", grader) == [str(len(DOCTOR_CHECKS))]
    assert re.findall(r"expected (\d+) findings", grader) == [str(len(DOCTOR_CHECKS))]
