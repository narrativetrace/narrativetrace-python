# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Integration tests for the structural artifact / last-green delta / approval-mode wiring in the
narrativetrace pytest plugin — mirrors the reference runtime's ``LastGreenLifecycleTest`` and
``InvocationArtifactTest`` end to end, through real ``pytest`` subprocesses.
"""

from __future__ import annotations

import json

import pytest

_BASELINE_SOURCE = """
from narrativetrace.trace_object import trace_object

class Svc:
    def run(self):
        return "ok"

    def extra(self):
        return "extra"

def test_place_order(narrative_trace):
    svc = trace_object(Svc(), narrative_trace)
    svc.run()
"""

_CHANGED_SOURCE = """
from narrativetrace.trace_object import trace_object

class Svc:
    def run(self):
        return "ok"

    def extra(self):
        return "extra"

def test_place_order(narrative_trace):
    svc = trace_object(Svc(), narrative_trace)
    svc.run()
    svc.extra()
"""

_CHANGED_AND_FAILING_SOURCE = """
from narrativetrace.trace_object import trace_object

class Svc:
    def run(self):
        return "ok"

    def extra(self):
        return "extra"

def test_place_order(narrative_trace):
    svc = trace_object(Svc(), narrative_trace)
    svc.run()
    svc.extra()
    assert False
"""


def test_an_ordinary_test_writes_a_structural_artifact_and_manifest_row(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(_BASELINE_SOURCE)
    result = pytester.runpytest_subprocess("-s")
    result.assert_outcomes(passed=1)

    nt_files = list(out_dir.rglob("test_place_order.nt"))
    assert len(nt_files) == 1
    content = nt_files[0].read_text(encoding="utf-8")
    assert content.startswith("scenario: Test place order\n")
    assert "Svc.run()" in content

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    row = manifest["scenarios"][0]
    assert row["testMethod"] == "test_place_order"
    assert "invocation" not in row
    assert row["artifacts"]["structural"].endswith("test_place_order.nt")

    result.stdout.fnmatch_lines(["*Since last green: 1 scenario new*"])


def test_the_suite_footer_reports_unchanged_on_a_second_identical_run(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(_BASELINE_SOURCE)
    pytester.runpytest_subprocess("-s").assert_outcomes(passed=1)
    second = pytester.runpytest_subprocess("-s")
    second.assert_outcomes(passed=1)
    second.stdout.fnmatch_lines(["*Since last green: 1 scenario unchanged*"])


def test_a_failing_run_with_changed_structure_leaves_the_baseline_untouched(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(_BASELINE_SOURCE)
    pytester.runpytest_subprocess("-s").assert_outcomes(passed=1)
    nt_file = next(out_dir.rglob("test_place_order.nt"))
    baseline_bytes = nt_file.read_bytes()

    # Add a call and fail the test: the delta must not advance the baseline.
    pytester.makepyfile(_CHANGED_AND_FAILING_SOURCE)
    failing = pytester.runpytest_subprocess("-s")
    failing.assert_outcomes(failed=1)
    failing.stdout.fnmatch_lines(["*Changed since last green*"])
    assert nt_file.read_bytes() == baseline_bytes

    # Revert: back to the original source, passing again -- reports unchanged, never a removal.
    pytester.makepyfile(_BASELINE_SOURCE)
    reverted = pytester.runpytest_subprocess("-s")
    reverted.assert_outcomes(passed=1)
    reverted.stdout.fnmatch_lines(["*Since last green: 1 scenario unchanged*"])
    assert nt_file.read_bytes() == baseline_bytes


def test_an_accepted_change_advances_the_last_green_artifact(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(_BASELINE_SOURCE)
    pytester.runpytest_subprocess("-s").assert_outcomes(passed=1)
    nt_file = next(out_dir.rglob("test_place_order.nt"))
    baseline_bytes = nt_file.read_bytes()

    pytester.makepyfile(_CHANGED_SOURCE)
    accepted = pytester.runpytest_subprocess("-s")
    accepted.assert_outcomes(passed=1)
    accepted.stdout.fnmatch_lines(["*Since last green: 1 scenario changed*"])
    assert nt_file.read_bytes() != baseline_bytes
    assert b"extra" in nt_file.read_bytes()


def test_approval_mode_fails_with_no_baseline_then_passes_once_approved(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved_dir = pytester.path / "approved"
    monkeypatch.setenv("NARRATIVETRACE_APPROVAL", "true")
    monkeypatch.setenv("NARRATIVETRACE_APPROVED_DIR", str(approved_dir))
    pytester.makepyfile(_BASELINE_SOURCE)

    # Approval verification runs in the fixture's own teardown, so pytest reports this as a
    # teardown error rather than a call failure -- either way the run does not exit clean.
    first = pytester.runpytest_subprocess("-s")
    first.assert_outcomes(passed=1, errors=1)
    first.stdout.fnmatch_lines(["*No approved trace for scenario*"])
    received = next(approved_dir.rglob("*.received.nt"))
    approved = received.with_name(received.name.replace(".received.nt", ".approved.nt"))
    received.replace(approved)

    second = pytester.runpytest_subprocess("-s")
    second.assert_outcomes(passed=1)
    assert not received.exists()


def test_approval_mode_rejects_a_changed_structure_with_a_readable_diff(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved_dir = pytester.path / "approved"
    monkeypatch.setenv("NARRATIVETRACE_APPROVAL", "true")
    monkeypatch.setenv("NARRATIVETRACE_APPROVED_DIR", str(approved_dir))
    pytester.makepyfile(_BASELINE_SOURCE)
    pytester.runpytest_subprocess("-s").assert_outcomes(passed=1, errors=1)
    received = next(approved_dir.rglob("*.received.nt"))
    approved = received.with_name(received.name.replace(".received.nt", ".approved.nt"))
    received.replace(approved)
    pytester.runpytest_subprocess("-s").assert_outcomes(passed=1)

    pytester.makepyfile(_CHANGED_SOURCE)
    changed = pytester.runpytest_subprocess("-s")
    changed.assert_outcomes(passed=1, errors=1)
    changed.stdout.fnmatch_lines(["*Structure changed against the approved trace*"])
    assert next(approved_dir.rglob("*.received.nt")).is_file()
