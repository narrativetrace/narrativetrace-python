# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The doctor's finding count the skills verify against is the registry's count (cross-port item
7): a check added to the doctor — a framework-table row, most often — moves every published count
in one change, and this test is what notices the one that did not."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
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


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROBE = _REPO_ROOT / "contract-probe/src/contract_probe/probes/narrativetrace_doctor_probe.py"
_NUMBER_WORDS = {18: "eighteen", 19: "nineteen", 20: "twenty", 21: "twenty-one"}


def test_the_contract_probe_reads_this_checkouts_doctor_report_as_well_formed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nightly 2026-10-11: the probe's id list lagged the doctor by ``config.approval-mode`` and
    read the PUBLISHED 0.3.0 as ``malformed`` — a probe, not a product, defect. The probe module is
    loaded by path (it is stdlib-only) and run against the doctor this checkout ships."""
    monkeypatch.chdir(_REPO_ROOT)
    spec = importlib.util.spec_from_file_location("narrativetrace_doctor_probe", _PROBE)
    assert spec is not None and spec.loader is not None
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    assert probe.observe() == "well-formed"


def test_the_contract_claim_counts_every_registered_check() -> None:
    contract = (_REPO_ROOT / "documentation/contract.yaml").read_text(encoding="utf-8")
    claim = re.search(
        r"id: config-shape-narrativetrace-doctor\n.*?claim: \"([^\"]*)\"", contract, re.S
    )
    assert claim is not None
    assert f"exactly the {_NUMBER_WORDS[len(DOCTOR_CHECKS)]} documented" in claim.group(1)
