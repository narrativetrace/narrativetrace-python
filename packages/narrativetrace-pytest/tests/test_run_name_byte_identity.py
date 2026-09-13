# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Ruling item 3's proof, executed rather than merely argued (2026-09-13): the run name and id
never enter the structural ``.nt`` text, the manifest's per-scenario rows, or the delta
computation -- only the run name differs when the identical scenario runs as two separate
test-suite executions.

Each :meth:`pytest.Pytester.runpytest_subprocess` call is a genuinely separate ``pytest``
process with its own session, so :func:`narrativetrace_pytest.plugin.pytest_sessionstart`
generates a fresh :class:`~narrativetrace.output.run_identity.RunIdentity` each time -- no
in-process module-caching workaround needed (unlike ``contract_probe``'s ``pytest.main()``-based
harness, which calls the same fixture more than once in one interpreter and needs a UUID-suffixed
module name to avoid colliding in ``sys.modules``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURE_SOURCE = """
from narrativetrace.trace_object import trace_object

class OrderService:
    def place_order(self, customer_id):
        return f"ORD-{customer_id}"

def test_places_an_order(narrative_trace):
    svc = trace_object(OrderService(), narrative_trace)
    assert svc.place_order("cust-1") == "ORD-cust-1"
"""


def _run_fixture(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, out_dir: Path
) -> pytest.RunResult:
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "true")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    result = pytester.runpytest_subprocess("-s")
    result.assert_outcomes(passed=1)
    return result


def _run_line(result: pytest.RunResult) -> str:
    for line in result.outlines:
        stripped = line.strip()
        if stripped.startswith("run: "):
            return stripped
    raise AssertionError(f"no 'run: <phrase>' line in output: {result.outlines}")


def _one_structural_file(out_dir: Path) -> Path:
    (structural,) = out_dir.rglob("*.nt")
    return structural


def _one_trace_markdown_file(out_dir: Path) -> Path:
    (trace,) = (p for p in out_dir.rglob("*.md") if p.name != "clarity-report.md")
    return trace


def _frontmatter_fields(markdown_file: Path) -> dict[str, str]:
    """The ``key: value`` lines between the document's opening and closing ``---``."""
    lines = markdown_file.read_text(encoding="utf-8").splitlines()
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            break
        colon = line.find(": ")
        if colon > 0:
            fields[line[:colon]] = line[colon + 2 :]
    return fields


class TestRunNameByteIdentity:
    def test_two_runs_produce_byte_identical_structural_artifacts(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytester.makepyfile(_FIXTURE_SOURCE)
        out_one, out_two = pytester.path / "out-one", pytester.path / "out-two"

        _run_fixture(pytester, monkeypatch, out_one)
        _run_fixture(pytester, monkeypatch, out_two)

        structural_one = _one_structural_file(out_one).read_text(encoding="utf-8")
        structural_two = _one_structural_file(out_two).read_text(encoding="utf-8")
        assert structural_one == structural_two

    def test_two_runs_name_different_runs_in_the_footer_and_manifest_while_scenarios_match(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytester.makepyfile(_FIXTURE_SOURCE)
        out_one, out_two = pytester.path / "out-one", pytester.path / "out-two"

        result_one = _run_fixture(pytester, monkeypatch, out_one)
        result_two = _run_fixture(pytester, monkeypatch, out_two)

        assert _run_line(result_one) != _run_line(result_two)

        manifest_one = json.loads((out_one / "manifest.json").read_text(encoding="utf-8"))
        manifest_two = json.loads((out_two / "manifest.json").read_text(encoding="utf-8"))
        assert manifest_one["scenarios"] == manifest_two["scenarios"]
        assert manifest_one["run"]["id"] != manifest_two["run"]["id"]
        assert manifest_one["run"]["name"] != manifest_two["run"]["name"]

    def test_the_markdown_frontmatter_differs_only_in_its_run_line(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only the frontmatter's own ``run:`` field is under test here: ``duration_ms``,
        ``trace_id`` and ``trace_name`` are real wall-clock timing or the TRACE's own (unrelated,
        randomly generated) identity -- both legitimately differ between two genuinely separate
        executions, and asserting past them would make this an eventual-consistency test on the
        clock (release-lessons rule 3)."""
        pytester.makepyfile(_FIXTURE_SOURCE)
        out_one, out_two = pytester.path / "out-one", pytester.path / "out-two"

        _run_fixture(pytester, monkeypatch, out_one)
        _run_fixture(pytester, monkeypatch, out_two)

        fields_one = _frontmatter_fields(_one_trace_markdown_file(out_one))
        fields_two = _frontmatter_fields(_one_trace_markdown_file(out_two))

        assert "run" in fields_one
        assert "run" in fields_two
        assert fields_one["run"] != fields_two["run"]
        assert fields_one["type"] == fields_two["type"]
        assert fields_one["scenario"] == fields_two["scenario"]
        assert fields_one["entry_point"] == fields_two["entry_point"]
        assert fields_one["method_count"] == fields_two["method_count"]
        assert fields_one["error_count"] == fields_two["error_count"]
